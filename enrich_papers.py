#!/usr/bin/env python3
"""
Use Claude CLI to enrich papers with key insights and categories.
"""

import csv
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

def generate_categories(papers):
    """Use Claude to generate categories by analyzing ALL paper titles."""
    print(f"Generating categories by analyzing ALL {len(papers)} paper titles...\n")

    # Prepare all paper titles
    titles_text = "\n".join([
        f"{i+1}. {paper['title']} (score: {paper['score']})"
        for i, paper in enumerate(papers)
    ])

    prompt = f"""Analyze these {len(papers)} NeurIPS 2025 paper titles and create high-level research categories that would effectively group them.

Paper titles:

{titles_text}

Based on these titles, create research categories that:
- Are clear and distinct
- Cover the major research themes across all papers
- Would be useful for organizing and browsing this collection
- Use standard ML/AI terminology
- Be concise - create a focused set of high-level categories that capture the main themes without being overly granular

The goal is meaningful, high-level groupings. Avoid creating too many categories - aim for broad themes that multiple papers can fit into.

Return ONLY a JSON array of category names, nothing else:
["Category 1", "Category 2", ...]"""

    try:
        result = subprocess.run(
            ['claude', '--print'],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            print(f"Error generating categories: {result.stderr}")
            return ["Machine Learning", "Deep Learning", "NLP", "Computer Vision", "Reinforcement Learning", "Other"]

        response_text = result.stdout.strip()

        # Extract JSON from response
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        # Try to find JSON array in the response
        import re
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)

        categories = json.loads(response_text)
        print(f"✓ Generated {len(categories)} categories")
        return categories

    except Exception as e:
        print(f"Error generating categories: {e}")
        return ["Machine Learning", "Deep Learning", "NLP", "Computer Vision", "Reinforcement Learning", "Other"]

def enrich_single_paper(paper, categories, index, total):
    """Enrich a single paper with key insights and category assignment."""
    title = paper['title']
    score = paper['score']
    pdf_url = paper.get('pdf_url', '')

    print(f"[{index}/{total}] Processing: {title[:60]}...")

    categories_str = ", ".join(categories)

    if not pdf_url:
        print(f"  ⚠ No PDF URL in data - will search for paper")
        prompt = f"""Find and read this NeurIPS 2025 paper, then extract key insights.

Paper Title: "{title}"
Relevance Score: {score} (higher = more aligned with agent systems, benchmarking, and tool use)

Available Categories: {categories_str}

Please:
1. Search the web for "{title} NeurIPS 2025 PDF" to find the paper (try Google Scholar, ArXiv, NeurIPS proceedings, author's page, etc.)
2. Once you find it, read the paper"""
    else:
        prompt = f"""Read this NeurIPS 2025 paper and extract key insights.

Paper Title: "{title}"
Paper URL: {pdf_url}
Relevance Score: {score} (higher = more aligned with agent systems, benchmarking, and tool use)

Available Categories: {categories_str}

Please:
1. Try to fetch and read the paper from the URL above
2. If the PDF link doesn't work or returns an error, search the web for "{title} NeurIPS 2025 PDF" to find an alternative link (Google Scholar, ArXiv, author's page, etc.) and read it from there"""

    prompt += f"""
3. Extract the key findings: What is new? What is important? What does this paper bring to the field?
4. Summarize what the paper is about (2-3 sentences)
5. Identify the main contribution or innovation (1-2 sentences)
6. IMPORTANT: Explain what makes this work NOVEL - how is it different from previous work? What existing limitations does it address? What new approach does it take? (2-3 sentences)
7. Assign 1-3 relevant categories from the list above - be selective and only choose the most relevant ones

IMPORTANT: Return ONLY a valid JSON object with this exact format, no other text before or after:
{{
    "key_findings": "What is new, important, and what the paper brings to the field",
    "description": "What the paper is about",
    "key_contribution": "Main contribution or innovation",
    "novelty": "How this work differs from previous work - what limitations it addresses, what new approach it takes, what makes it novel",
    "categories": ["Category1", "Category2"]
}}"""

    # Try with longer timeout for large papers
    max_retries = 2
    for attempt in range(max_retries):
        try:
            timeout_seconds = 300 if attempt == 0 else 420  # 5 min, then 7 min
            result = subprocess.run(
                ['claude', '--print', '--tools', 'WebSearch', 'WebFetch', '--allowedTools', 'WebSearch', 'WebFetch'],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )

            if result.returncode != 0:
                if attempt < max_retries - 1:
                    print(f"  ⟳ Retry {attempt + 1}/{max_retries - 1}...")
                    continue
                print(f"  ✗ Error after {max_retries} attempts")
                return None

            # Success - break out of retry loop
            break

        except subprocess.TimeoutExpired:
            if attempt < max_retries - 1:
                print(f"  ⏱ Timeout ({timeout_seconds}s) - retry {attempt + 1}/{max_retries - 1}...")
                continue
            print(f"  ✗ Timeout after {max_retries} attempts (paper likely too large)")
            return None
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⟳ Error: {e} - retry {attempt + 1}/{max_retries - 1}...")
                continue
            print(f"  ✗ Error after {max_retries} attempts: {e}")
            return None

    response_text = result.stdout.strip()

    # Extract JSON from response
    try:
        if not response_text:
            print(f"  ✗ Empty response from Claude")
            return None

        # Remove markdown code blocks if present
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        # Try to find JSON object in the response (improved regex for nested objects)
        import re
        # Look for the first { and find its matching }
        start = response_text.find('{')
        if start == -1:
            print(f"  ✗ No JSON object found in response")
            print(f"     Response preview: {response_text[:300]}")
            return None

        # Count braces to find the matching closing brace
        brace_count = 0
        end = start
        for i in range(start, len(response_text)):
            if response_text[i] == '{':
                brace_count += 1
            elif response_text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break

        if brace_count != 0:
            print(f"  ✗ Malformed JSON - unmatched braces")
            return None

        json_str = response_text[start:end]
        enrichment = json.loads(json_str)

        # Validate that we got the expected fields
        if not isinstance(enrichment, dict):
            print(f"  ✗ Response is not a JSON object")
            return None

        print(f"  ✓ Read PDF - Categories: {', '.join(enrichment.get('categories', []))}")
        return enrichment

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse error: {e}")
        print(f"     Response preview: {response_text[:300]}")
        return None
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return None

def enrich_papers(csv_file, output_file, max_workers=50, dry_run=False):
    """Enrich ALL papers with key insights and categories."""

    # Read papers
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        papers = list(reader)

    if dry_run:
        print(f"🧪 DRY RUN MODE: Processing only first 10 papers\n")
        papers = papers[:10]
        max_workers = min(max_workers, 10)
    else:
        print(f"Loaded {len(papers)} papers\n")

    # Required fields for a complete enrichment
    REQUIRED_FIELDS = ['key_findings', 'description', 'key_contribution', 'novelty', 'ai_categories']

    # Load existing enriched data if available
    existing_enriched = {}
    existing_categories = []
    existing_data = {'papers': [], 'categories': []}

    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                existing_categories = existing_data.get('categories', [])
                existing_papers = existing_data.get('papers', [])

                # Create lookup by title
                for paper in existing_papers:
                    # Check if paper has all required fields and they're not empty
                    is_complete = all(
                        field in paper and paper.get(field)
                        for field in REQUIRED_FIELDS
                    )

                    if is_complete:
                        existing_enriched[paper['title']] = paper

                print(f"📁 Found existing enrichment file with {len(existing_enriched)} fully enriched papers")
        except Exception as e:
            print(f"⚠ Could not load existing enrichment: {e}")

    # Filter out papers that are already enriched
    papers_to_enrich = []
    already_enriched_papers = []
    incomplete_papers = []

    for paper in papers:
        title = paper['title']
        if title in existing_enriched:
            # Check if PDF URL changed (might need re-enrichment)
            existing_pdf = existing_enriched[title].get('pdf_url', '')
            current_pdf = paper.get('pdf_url', '')

            if existing_pdf == current_pdf:
                # Paper already enriched and hasn't changed
                already_enriched_papers.append(existing_enriched[title])
            else:
                # PDF URL changed, re-enrich
                print(f"  ⟳ PDF URL changed for: {title[:60]}... (will re-enrich)")
                papers_to_enrich.append(paper)
        else:
            # Check if paper exists in old data but is incomplete
            for old_paper in existing_data.get('papers', []):
                if old_paper['title'] == title:
                    # Paper exists but wasn't in existing_enriched, so it's incomplete
                    incomplete_papers.append(title)
                    break
            papers_to_enrich.append(paper)

    if incomplete_papers:
        print(f"⚠ Found {len(incomplete_papers)} incomplete papers (missing required fields) - will re-enrich")

    print(f"✓ {len(already_enriched_papers)} papers fully enriched (skipping)")
    print(f"→ {len(papers_to_enrich)} papers to enrich ({len(incomplete_papers)} incomplete, {len(papers_to_enrich) - len(incomplete_papers)} new)\n")

    # Step 1: Generate categories
    # If we have existing categories and are only enriching a few new papers, reuse them
    if existing_categories and len(papers_to_enrich) < len(papers) * 0.5:
        print(f"Reusing existing {len(existing_categories)} categories: {', '.join(existing_categories)}\n")
        categories = existing_categories
    else:
        # Generate fresh categories based on all papers
        categories = generate_categories(papers)
        print(f"\nGenerated {len(categories)} categories: {', '.join(categories)}\n")

    # Step 2: Enrich papers in parallel
    if len(papers_to_enrich) == 0:
        print("✓ All papers already enriched! Nothing to do.\n")
        # Just save the existing data to ensure categories are up to date
        output_data = {
            'categories': categories,
            'papers': already_enriched_papers
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"✓ Saved {len(already_enriched_papers)} papers to {output_file}")
        return

    if dry_run:
        print(f"Enriching {len(papers_to_enrich)} papers with key insights (DRY RUN)...")
        print(f"Running {max_workers} parallel workers.\n")
    else:
        print(f"Enriching {len(papers_to_enrich)} new/changed papers with key insights...")
        print(f"Running {max_workers} parallel workers for maximum speed.\n")

    newly_enriched_papers = []
    completed_count = 0

    # Helper function to save progress
    def save_progress():
        # Combine already enriched with newly enriched
        all_papers = already_enriched_papers + newly_enriched_papers
        output_data = {
            'categories': categories,
            'papers': all_papers
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks (only for papers that need enrichment)
        future_to_paper = {
            executor.submit(enrich_single_paper, paper, categories, i+1, len(papers_to_enrich)): paper
            for i, paper in enumerate(papers_to_enrich)
        }

        # Collect results as they complete
        for future in as_completed(future_to_paper):
            paper = future_to_paper[future]
            try:
                enrichment = future.result()

                # Add enrichment to paper
                enriched_paper = paper.copy()
                if enrichment:
                    enriched_paper['key_findings'] = enrichment.get('key_findings', '')
                    enriched_paper['description'] = enrichment.get('description', '')
                    enriched_paper['key_contribution'] = enrichment.get('key_contribution', '')
                    enriched_paper['novelty'] = enrichment.get('novelty', '')
                    enriched_paper['ai_categories'] = enrichment.get('categories', [])
                else:
                    enriched_paper['key_findings'] = ''
                    enriched_paper['description'] = ''
                    enriched_paper['key_contribution'] = ''
                    enriched_paper['novelty'] = ''
                    enriched_paper['ai_categories'] = []

                newly_enriched_papers.append(enriched_paper)

            except Exception as e:
                print(f"  ✗ Exception: {e}")
                enriched_paper = paper.copy()
                enriched_paper['key_findings'] = ''
                enriched_paper['description'] = ''
                enriched_paper['key_contribution'] = ''
                enriched_paper['novelty'] = ''
                enriched_paper['ai_categories'] = []
                newly_enriched_papers.append(enriched_paper)

            # Save progress every 5 papers
            completed_count += 1
            if completed_count % 5 == 0:
                save_progress()
                print(f"\n💾 Progress saved: {completed_count}/{len(papers_to_enrich)} papers completed ({len(already_enriched_papers)} already enriched)\n")

    # Final save
    save_progress()
    print(f"\n✓ Saved enriched paper data to {output_file}")

    # Print summary
    all_enriched_papers = already_enriched_papers + newly_enriched_papers
    successfully_enriched = sum(1 for p in all_enriched_papers if p.get('key_findings'))
    print(f"\nSummary:")
    print(f"  Previously enriched: {len(already_enriched_papers)}")
    print(f"  Newly enriched: {len(newly_enriched_papers)}")
    print(f"  Total papers: {len(all_enriched_papers)}")
    print(f"  Successfully enriched: {successfully_enriched}/{len(all_enriched_papers)}")
    print(f"  Categories: {len(categories)}")

    # Show a sample from newly enriched
    if len(newly_enriched_papers) > 0:
        samples_with_findings = [p for p in newly_enriched_papers if p.get('key_findings')]
        if samples_with_findings:
            sample = samples_with_findings[0]
            print(f"\n📄 Sample newly enriched paper:")
            print(f"  Title: {sample['title'][:80]}...")
            print(f"  Key Findings: {sample['key_findings'][:150]}...")
            print(f"  Categories: {', '.join(sample.get('ai_categories', []))}")

    # Show category distribution
    category_counts = {}
    for paper in all_enriched_papers:
        for cat in paper.get('ai_categories', []):
            category_counts[cat] = category_counts.get(cat, 0) + 1

    print(f"\n📊 Papers per Category:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count} papers")

if __name__ == "__main__":
    import sys

    csv_file = "neurips2025_positive_scores.csv"
    output_file = "enriched_papers.json"

    # Check for dry-run mode
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv

    if dry_run:
        print("=" * 80)
        print("🧪 DRY RUN MODE ENABLED")
        print("=" * 80)
        print("Will process only the first 10 papers to test the enrichment process.")
        print("Run without --dry-run flag to process all 370 papers.\n")
        output_file = "enriched_papers_dry_run.json"

    # Enrich papers with 50 parallel workers for maximum speed
    # Dry run: ~2-3 minutes for 10 papers
    # Full run: ~10-15 minutes for 370 papers
    enrich_papers(csv_file, output_file, max_workers=50, dry_run=dry_run)
