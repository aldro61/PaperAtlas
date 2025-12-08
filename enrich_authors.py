#!/usr/bin/env python3
"""
Use Claude CLI to enrich top authors with affiliation and role information.
"""

import csv
import json
import os
import subprocess
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

def parse_authors(author_string):
    """Parse author string into individual authors."""
    if not author_string:
        return []

    authors = [a.strip() for a in author_string.split(',')]
    cleaned = []
    for author in authors:
        if author in ['...', 'et al', 'et al.']:
            continue
        author = author.rstrip('.')
        if author:
            cleaned.append(author)

    return cleaned

def analyze_authors(papers, first_last_only=True):
    """Analyze authors and return statistics.

    Args:
        papers: List of papers to analyze
        first_last_only: If True, only consider first, second, and last authors (default: True)
    """
    author_papers = defaultdict(list)
    author_scores = defaultdict(list)
    author_engagement = defaultdict(lambda: {'relevant': 0, 'reads': 0})

    for paper in papers:
        authors = parse_authors(paper['authors'])
        score = int(paper['score'])
        relevant = int(paper['relevant_to_users']) if paper['relevant_to_users'] else 0
        reads = int(paper['read_by_users']) if paper['read_by_users'] else 0

        # Filter to first, second, and last authors if enabled
        if first_last_only and len(authors) > 3:
            # Keep first, second, and last author
            authors = [authors[0], authors[1], authors[-1]]
        elif first_last_only and len(authors) == 3:
            # All three are important
            pass
        elif first_last_only and len(authors) == 2:
            # Both authors are important
            pass
        # If only 1 author or first_last_only=False, keep all

        for author in authors:
            author_papers[author].append({
                'title': paper['title'],
                'score': score
            })
            author_scores[author].append(score)
            author_engagement[author]['relevant'] += relevant
            author_engagement[author]['reads'] += reads

    # Calculate statistics
    author_stats = []
    for author, papers_list in author_papers.items():
        avg_score = sum(author_scores[author]) / len(author_scores[author])
        max_score = max(author_scores[author])
        total_relevant = author_engagement[author]['relevant']
        total_reads = author_engagement[author]['reads']

        # Count highly relevant papers (score >= 85 - strong alignment with user's interests)
        highly_relevant_count = sum(1 for score in author_scores[author] if score >= 85)

        author_stats.append({
            'name': author,
            'paper_count': len(papers_list),
            'highly_relevant_count': highly_relevant_count,
            'avg_score': round(avg_score, 1),
            'max_score': max_score,
            'total_relevant': total_relevant,
            'total_reads': total_reads,
            'papers': papers_list
        })

    return author_stats

def get_author_info_with_claude(author_name, paper_titles):
    """Use Claude CLI to get author affiliation and role."""

    # Create a prompt for Claude
    prompt = f"""I need to find the academic affiliation, role, photo, and profile link for this researcher presenting at NeurIPS 2025:

Author: {author_name}

Their NeurIPS 2025 papers include:
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
        import re
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
        author['affiliation'] = author_info.get('affiliation', 'Unknown')
        author['role'] = author_info.get('role', 'Unknown')
        author['photo_url'] = author_info.get('photo_url', None)
        author['profile_url'] = author_info.get('profile_url', None)
        photo_status = "📸" if author['photo_url'] else ""
        link_status = "🔗" if author['profile_url'] else ""
        print(f"  ✓ {author['affiliation']} - {author['role']} {photo_status}{link_status}")
    else:
        author['affiliation'] = 'Unknown'
        author['role'] = 'Unknown'
        author['photo_url'] = None
        author['profile_url'] = None
        print(f"  ⚠ Could not find information")

    return author

def enrich_authors(csv_file, output_file, max_workers=30, first_last_only=True):
    """Enrich all authors with at least 1 highly relevant paper (score >= 85).

    Args:
        csv_file: Path to CSV file with papers
        output_file: Path to output JSON file
        max_workers: Number of parallel workers
        first_last_only: Only consider first, second, and last authors (default: True)
    """

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

                # Create lookup by name
                for author in existing_authors:
                    # Check if author has all required fields (allow empty photo/profile URLs)
                    is_complete = all(field in author for field in REQUIRED_FIELDS)
                    # Also check that affiliation and role are not 'Unknown' or empty
                    has_info = (
                        is_complete and
                        author.get('affiliation') and
                        author.get('affiliation') != 'Unknown' and
                        author.get('role') and
                        author.get('role') != 'Unknown'
                    )

                    if has_info:
                        existing_enriched[author['name']] = author

                print(f"📁 Found existing enrichment file with {len(existing_enriched)} fully enriched authors")
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

    print(f"✓ {len(already_enriched_authors)} authors fully enriched (skipping)")
    print(f"→ {len(authors_to_enrich)} authors to enrich\n")

    if len(authors_to_enrich) == 0:
        print("✓ All authors already enriched! Nothing to do.\n")
        # Save existing data
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(already_enriched_authors, f, ensure_ascii=False, indent=2)
        print(f"✓ Saved {len(already_enriched_authors)} authors to {output_file}")
        return

    print(f"Enriching {len(authors_to_enrich)} new authors with at least 1 highly relevant paper (score >= 85)...")
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
        print(f"   {author['highly_relevant_count']} highly relevant papers (≥85), {author['paper_count']} total, avg: {author['avg_score']}")

if __name__ == "__main__":
    csv_file = "neurips2025_positive_scores.csv"
    output_file = "enriched_authors.json"

    # Enrich all authors with at least 1 highly relevant paper (score >= 85)
    # Running 15 parallel workers (reduced from 30 since we're now fetching pages)
    enrich_authors(csv_file, output_file, max_workers=15)
