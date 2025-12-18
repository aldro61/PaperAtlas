#!/usr/bin/env python3
"""
Use Claude CLI to enrich top authors with affiliation and role information.
"""

import csv
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import HIGHLY_RELEVANT_THRESHOLD, AUTHOR_ENRICHMENT_WORKERS
from utils import parse_authors, analyze_authors

def get_author_info_with_claude(author_name, paper_titles):
    """Use Claude CLI to get author affiliation and role."""

    # Create a prompt for Claude
    prompt = f"""I need to find the academic affiliation, role, photo, and profile link for this researcher:

Author: {author_name}

Their papers include:
{chr(10).join(f"- {title[:100]}" for title in paper_titles[:3])}

Please search for this researcher's information:
1. Their university/company affiliation
2. Their role (e.g., PhD Student, Postdoc, Assistant Professor, Research Scientist, etc.)
3. A professional photo URL (from their university/company webpage, Google Scholar, LinkedIn, or research profile)
4. A link to their profile (prioritize: personal webpage > Google Scholar > university profile page)

Return ONLY a JSON object with this exact format (no other text):
{{"affiliation": "Institution Name", "role": "Role Title", "photo_url": "https://...", "profile_url": "https://..."}}

If you cannot find a photo or profile link, set those fields to null. If you cannot find clear affiliation/role information, use "Unknown"."""

    # Try with retries and longer timeout
    max_retries = 2
    for attempt in range(max_retries):
        try:
            timeout_seconds = 120 if attempt == 0 else 180  # 2 min, then 3 min
            result = subprocess.run(
                ['claude', '--print', '--tools', 'WebSearch', 'WebFetch', '--allowedTools', 'WebSearch', 'WebFetch'],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )

            if result.returncode != 0:
                if attempt < max_retries - 1:
                    print(f"  ⟳ Error - retry {attempt + 1}/{max_retries - 1}...")
                    continue
                print(f"  ✗ Error for {author_name} after {max_retries} attempts")
                if result.stderr:
                    print(f"     stderr: {result.stderr[:200]}")
                return None

            # Success - break out of retry loop
            break

        except subprocess.TimeoutExpired:
            if attempt < max_retries - 1:
                print(f"  ⏱ Timeout ({timeout_seconds}s) - retry {attempt + 1}/{max_retries - 1}...")
                continue
            print(f"  ✗ Timeout for {author_name} after {max_retries} attempts")
            return None
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⟳ Error: {e} - retry {attempt + 1}/{max_retries - 1}...")
                continue
            print(f"  ✗ Error for {author_name} after {max_retries} attempts: {e}")
            return None

    response_text = result.stdout.strip()

    # Extract JSON from response
    try:
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        # Try to find JSON in the response
        json_match = re.search(r'\{[^}]+\}', response_text)
        if json_match:
            response_text = json_match.group(0)

        author_info = json.loads(response_text)
        return author_info

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON decode error for {author_name}: {e}")
        print(f"     Response: {response_text[:200]}")
        return None

def process_single_author(author, index, total):
    """Process a single author - for parallel execution."""
    print(f"[{index}/{total}] {author['name']} ({author['highly_relevant_count']} highly relevant, {author['paper_count']} total)")

    paper_titles = [p['title'] for p in author['papers']]
    author_info = get_author_info_with_claude(author['name'], paper_titles)

    if author_info:
        affiliation = author_info.get('affiliation') or 'Unknown'
        role = author_info.get('role') or 'Unknown'
        author['affiliation'] = affiliation
        author['role'] = role
        author['photo_url'] = author_info.get('photo_url', None)
        author['profile_url'] = author_info.get('profile_url', None)
        photo_status = "📸" if author['photo_url'] else ""
        link_status = "🔗" if author['profile_url'] else ""
        author['enrichment_status'] = 'success' if (affiliation != 'Unknown' and role != 'Unknown') else 'not_found'
        print(f"  ✓ {author['affiliation']} - {author['role']} {photo_status}{link_status}")
    else:
        author['affiliation'] = 'Unknown'
        author['role'] = 'Unknown'
        author['photo_url'] = None
        author['profile_url'] = None
        author['enrichment_status'] = 'not_found'
        print(f"  ⚠ Could not find information")

    return author

def enrich_authors(csv_file, output_file, max_workers=None, first_last_only=True):
    """Enrich all authors with at least 1 highly relevant paper.

    Args:
        csv_file: Path to CSV file with papers
        output_file: Path to output JSON file
        max_workers: Number of parallel workers (default: from config)
        first_last_only: Only consider first, second, and last authors (default: True)
    """
    if max_workers is None:
        max_workers = AUTHOR_ENRICHMENT_WORKERS

    # Read papers
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        papers = list(reader)

    print(f"Loaded {len(papers)} papers")

    # Required fields for a complete enrichment
    REQUIRED_FIELDS = ['affiliation', 'role', 'photo_url', 'profile_url']

    # Load existing enriched data if available
    existing_enriched = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_authors = json.load(f)

                # Create lookup by name and track which authors were already attempted
                with_info = 0
                without_info = 0
                for author in existing_authors:
                    # Check if author has all required fields (allow empty photo/profile URLs)
                    is_complete = all(field in author for field in REQUIRED_FIELDS)
                    if not is_complete:
                        continue

                    has_affiliation = author.get('affiliation') and author.get('affiliation') != 'Unknown'
                    has_role = author.get('role') and author.get('role') != 'Unknown'
                    has_known_info = has_affiliation and has_role

                    if has_known_info:
                        author.setdefault('enrichment_status', 'success')
                        with_info += 1
                    else:
                        # Mark as already attempted but unresolved so we can skip on retries
                        author['enrichment_status'] = author.get('enrichment_status', 'not_found')
                        without_info += 1

                    existing_enriched[author['name']] = author

                print(f"📁 Found existing enrichment file with {len(existing_enriched)} processed authors ({with_info} with info, {without_info} marked not found)")
        except Exception as e:
            print(f"⚠ Could not load existing enrichment: {e}")

    # Analyze authors
    if first_last_only:
        print("Analyzing authors (first, second, and last authors)...")
    else:
        print("Analyzing authors (all authors)...")
    author_stats = analyze_authors(papers, first_last_only=first_last_only)

    # Filter to authors with at least 1 highly relevant paper and sort
    qualifying_authors = [a for a in author_stats if a['highly_relevant_count'] >= 1]
    qualifying_authors.sort(key=lambda x: (x['highly_relevant_count'], x['paper_count']), reverse=True)

    # Filter out authors that are already enriched
    authors_to_enrich = []
    already_enriched_authors = []

    for author in qualifying_authors:
        if author['name'] in existing_enriched:
            # Author already enriched - use existing data
            already_enriched_authors.append(existing_enriched[author['name']])
        else:
            # Author needs enrichment
            authors_to_enrich.append(author)

    skipped_not_found = sum(1 for a in already_enriched_authors if a.get('enrichment_status') == 'not_found')
    skipped_with_info = len(already_enriched_authors) - skipped_not_found

    print(f"✓ {skipped_with_info} authors fully enriched (skipping)")
    if skipped_not_found:
        print(f"✓ {skipped_not_found} authors previously attempted but unresolved (skipping)")
    print(f"→ {len(authors_to_enrich)} authors to enrich\n")

    if len(authors_to_enrich) == 0:
        print("✓ All authors already enriched! Nothing to do.\n")
        # Save existing data
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(already_enriched_authors, f, ensure_ascii=False, indent=2)
        print(f"✓ Saved {len(already_enriched_authors)} authors to {output_file}")
        return

    print(f"Enriching {len(authors_to_enrich)} new authors with at least 1 highly relevant paper (score >= {HIGHLY_RELEVANT_THRESHOLD})...")
    print(f"Running {max_workers} parallel requests at a time.\n")

    newly_enriched_authors = []
    completed_count = 0

    # Helper function to save progress
    def save_progress():
        # Combine already enriched with newly enriched
        all_authors = already_enriched_authors + newly_enriched_authors
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_authors, f, ensure_ascii=False, indent=2)

    # Process authors in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks (only for authors that need enrichment)
        future_to_author = {
            executor.submit(process_single_author, author, i+1, len(authors_to_enrich)): author
            for i, author in enumerate(authors_to_enrich)
        }

        # Collect results as they complete
        for future in as_completed(future_to_author):
            try:
                enriched_author = future.result()
                newly_enriched_authors.append(enriched_author)
            except Exception as e:
                author = future_to_author[future]
                print(f"  ✗ Exception for {author['name']}: {e}")
                author['affiliation'] = 'Unknown'
                author['role'] = 'Unknown'
                author['photo_url'] = None
                author['profile_url'] = None
                author['enrichment_status'] = 'not_found'
                newly_enriched_authors.append(author)

            # Save progress every 3 authors
            completed_count += 1
            if completed_count % 3 == 0:
                save_progress()
                print(f"\n💾 Progress saved: {completed_count}/{len(authors_to_enrich)} authors completed ({len(already_enriched_authors)} already enriched)\n")

    # Final save
    save_progress()
    print(f"\n✓ Saved enriched author data to {output_file}")

    # Print summary
    all_authors = already_enriched_authors + newly_enriched_authors
    print(f"\nSummary:")
    print(f"  Previously enriched: {len(already_enriched_authors)}")
    print(f"  Newly enriched: {len(newly_enriched_authors)}")
    print(f"  Total authors: {len(all_authors)}")
    known_affiliations = sum(1 for a in all_authors if a.get('affiliation') and a['affiliation'] != 'Unknown')
    print(f"  Successfully found affiliations: {known_affiliations}/{len(all_authors)}")

    # Show top 10 with affiliations
    print(f"\n🎯 Top 10 Authors to Meet:")
    print("=" * 100)
    for i, author in enumerate(all_authors[:10], 1):
        print(f"\n{i}. {author['name']}")
        print(f"   {author['affiliation']} - {author['role']}")
        print(f"   {author['highly_relevant_count']} highly relevant papers (≥{HIGHLY_RELEVANT_THRESHOLD}), {author['paper_count']} total, avg: {author['avg_score']}")

if __name__ == "__main__":
    csv_file = "papers.csv"
    output_file = "enriched_authors.json"

    # Enrich all authors with at least 1 highly relevant paper
    enrich_authors(csv_file, output_file)
