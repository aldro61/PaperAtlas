#!/usr/bin/env python3
"""
Generate an HTML website with embedded paper data.
"""

import csv
import glob
import json
import os
import re
import sys

# Import synthesis generation and shared utilities
sys.path.append(os.path.dirname(__file__))
from config import HIGHLY_RELEVANT_THRESHOLD
try:
    from synthesize_conference import generate_synthesis
except ImportError:
    generate_synthesis = None

from utils import parse_authors, analyze_authors

def markdown_to_html(text, paper_titles=None):
    """Convert basic markdown to HTML with interactive paper references.

    Args:
        text: Markdown text to convert
        paper_titles: Optional dict mapping paper number to {title, score, categories}
    """
    if not text:
        return ""

    # Convert headers
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)

    # Convert bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Convert italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    # Convert links [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', text)

    # Convert paper references [Paper X] to interactive tooltips with PDF links
    if paper_titles:
        def replace_paper_ref(match):
            paper_num = match.group(1)
            if paper_num in paper_titles:
                info = paper_titles[paper_num]
                title = info['title'].replace('"', '&quot;').replace("'", '&#39;')
                score = info.get('score', 'N/A')
                categories = ', '.join(info.get('categories', []))
                pdf_url = info.get('pdf_url', '')

                # Store data attributes for JavaScript tooltip and PDF link
                pdf_attr = f' data-pdf-url="{pdf_url}"' if pdf_url else ''
                return f'<a class="paper-ref" href="{pdf_url}" target="_blank" data-paper-id="{paper_num}" data-title="{title}" data-score="{score}" data-categories="{categories}"{pdf_attr}>[Paper {paper_num}]</a>'
            return match.group(0)

        text = re.sub(r'\[Paper (\d+)\]', replace_paper_ref, text)

    # Convert paragraphs (double newline)
    paragraphs = text.split('\n\n')
    html_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if para:
            # Don't wrap if it's already a heading
            if para.startswith('<h') or para.startswith('<ul') or para.startswith('<ol'):
                html_paragraphs.append(para)
            else:
                # Replace single newlines with <br>
                para = para.replace('\n', '<br>')
                html_paragraphs.append(f'<p>{para}</p>')

    return '\n\n'.join(html_paragraphs)

def generate_paper_reference_list(paper_titles):
    """Generate a collapsible HTML reference list of all papers.

    Args:
        paper_titles: Dict mapping paper number (str) to {title, score, categories, pdf_url}

    Returns:
        HTML string with a collapsible reference list
    """
    if not paper_titles:
        return ""

    html = '''
<details style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
<summary style="cursor: pointer; font-weight: bold; font-size: 1.1em; color: #1c3664;">📚 Paper Reference Index ({} papers)</summary>
<div style="margin-top: 20px;">
'''.format(len(paper_titles))

    for paper_num in sorted(paper_titles.keys(), key=int):
        info = paper_titles[paper_num]
        title = info['title']
        score = info.get('score', 'N/A')
        categories = ', '.join(info.get('categories', []))
        pdf_url = info.get('pdf_url', '')

        pdf_link = f' <a href="{pdf_url}" target="_blank" style="color: #00c781; text-decoration: none;">📄 PDF</a>' if pdf_url else ''

        html += f'''<p style="margin: 10px 0; padding: 10px; background: white; border-radius: 5px;">
<strong>[Paper {paper_num}]</strong> {title}
<br><small style="color: #666;">Score: {score} | {categories}</small>{pdf_link}</p>
'''

    html += '</div>\n</details>'
    return html

def generate_website(csv_file, output_file, enriched_authors_file=None, enriched_papers_file=None, conference_title=None, synthesis_file=None):
    """Generate HTML website with embedded data.

    Can load papers from either:
    1. enriched_papers_file (JSON with full enrichment data) - preferred
    2. csv_file (basic paper data, optionally merged with enriched_papers_file)

    Args:
        csv_file: Path to papers CSV file
        output_file: Path for output HTML file
        enriched_authors_file: Optional path to enriched authors JSON
        enriched_papers_file: Optional path to enriched papers JSON
        conference_title: Optional conference title (e.g., "NeurIPS 2025"). If not provided, derived from filename.
        synthesis_file: Optional path to a pre-generated synthesis HTML/MD file.
    """

    papers = []
    all_categories = []

    # Try to load from enriched papers JSON first (preferred - contains all data)
    if enriched_papers_file and os.path.exists(enriched_papers_file):
        try:
            with open(enriched_papers_file, 'r', encoding='utf-8') as f:
                enriched_data = json.load(f)
                all_categories = enriched_data.get('categories', [])
                papers = enriched_data.get('papers', [])

                # Normalize field names for the website
                for paper in papers:
                    # Ensure 'score' field exists (website JS uses this)
                    if 'score' not in paper and 'relevance_score' in paper:
                        paper['score'] = paper['relevance_score']
                    # Ensure session_type exists for display
                    if 'session_type' not in paper and 'session_name' in paper:
                        paper['session_type'] = paper['session_name']

                print(f"Loaded {len(papers)} papers from enriched JSON")
                print(f"Found {len(all_categories)} categories: {', '.join(all_categories)}")
        except Exception as e:
            print(f"Warning: Could not load enriched papers JSON: {e}")
            papers = []

    # Fall back to CSV if no papers loaded from JSON
    if not papers and csv_file and os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            papers = list(reader)

        print(f"Loaded {len(papers)} papers from CSV")

        # Load enriched paper data if available and merge
        enriched_papers_data = {}
        if enriched_papers_file:
            try:
                with open(enriched_papers_file, 'r', encoding='utf-8') as f:
                    enriched_data = json.load(f)
                    all_categories = enriched_data.get('categories', [])
                    enriched_list = enriched_data.get('papers', [])

                    # Create lookup by title
                    for ep in enriched_list:
                        enriched_papers_data[ep['title']] = {
                            'key_findings': ep.get('key_findings', ''),
                            'description': ep.get('description', ''),
                            'key_contribution': ep.get('key_contribution', ''),
                            'novelty': ep.get('novelty', ''),
                            'ai_categories': ep.get('ai_categories', [])
                        }
                    print(f"Loaded enriched data for {len(enriched_papers_data)} papers")
                    print(f"Found {len(all_categories)} categories: {', '.join(all_categories)}")
            except FileNotFoundError:
                print(f"No enriched papers file found at {enriched_papers_file}")
            except Exception as e:
                print(f"Warning: Could not load enriched papers: {e}")

        # Merge enriched data with papers from CSV
        for paper in papers:
            # Normalize score field
            if 'score' not in paper and 'relevance_score' in paper:
                paper['score'] = paper['relevance_score']

            if paper['title'] in enriched_papers_data:
                enrichment = enriched_papers_data[paper['title']]
                paper['key_findings'] = enrichment['key_findings']
                paper['description'] = enrichment['description']
                paper['key_contribution'] = enrichment['key_contribution']
                paper['novelty'] = enrichment['novelty']
                paper['ai_categories'] = enrichment['ai_categories']
            else:
                paper['key_findings'] = ''
                paper['description'] = ''
                paper['key_contribution'] = ''
                paper['novelty'] = ''
                paper['ai_categories'] = []

    if not papers:
        print("Error: No papers found in either enriched JSON or CSV file")
        return

    # Analyze authors
    print("Analyzing authors...")
    author_stats = analyze_authors(papers)
    print(f"Found {len(author_stats)} unique authors")

    # Load enriched author data if available (supports JSON list or CSV)
    enriched_data = {}
    if enriched_authors_file:
        try:
            if enriched_authors_file.lower().endswith('.csv'):
                with open(enriched_authors_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get('name') or row.get('author') or row.get('author_name')
                        if not name:
                            continue
                        enriched_data[name] = {
                            'affiliation': row.get('affiliation', 'Unknown'),
                            'role': row.get('role', 'Unknown'),
                            'photo_url': row.get('photo_url') or None,
                            'profile_url': row.get('profile_url') or None
                        }
                print(f"Loaded enriched data for {len(enriched_data)} authors from CSV")
            else:
                with open(enriched_authors_file, 'r', encoding='utf-8') as f:
                    enriched_authors = json.load(f)
                    for author in enriched_authors:
                        enriched_data[author['name']] = {
                            'affiliation': author.get('affiliation', 'Unknown'),
                            'role': author.get('role', 'Unknown'),
                            'photo_url': author.get('photo_url', None),
                            'profile_url': author.get('profile_url', None)
                        }
                print(f"Loaded enriched data for {len(enriched_data)} authors from JSON")
        except FileNotFoundError:
            print(f"Warning: Enriched authors file not found at {enriched_authors_file}")
        except Exception as e:
            print(f"Warning: Could not load enriched authors: {e}")

    # Merge enriched data with author stats
    for author in author_stats:
        if author['name'] in enriched_data:
            author['affiliation'] = enriched_data[author['name']]['affiliation']
            author['role'] = enriched_data[author['name']]['role']
            author['photo_url'] = enriched_data[author['name']]['photo_url']
            author['profile_url'] = enriched_data[author['name']]['profile_url']
        else:
            author['affiliation'] = 'Unknown'
            author['role'] = 'Unknown'
            author['photo_url'] = None
            author['profile_url'] = None

        # Sort each author's papers by relevance score (desc), then title
        author['papers'].sort(
            key=lambda p: (
                float(p.get('score', 0) or 0),
                (p.get('title') or '')
            ),
            reverse=True,
        )

    # Sort authors by highly relevant papers, then average relevance score
    author_stats.sort(
        key=lambda a: (
            a.get('highly_relevant_count', 0),
            a.get('avg_score', 0),
        ),
        reverse=True,
    )

    # Load or generate synthesis if we have enriched papers
    synthesis_text = None
    enriched_paper_count = sum(1 for p in papers if p.get('key_findings'))

    # Build paper titles mapping for interactive tooltips
    paper_titles = {}
    enriched_papers = [p for p in papers if p.get('key_findings') and p.get('novelty')]
    for i, paper in enumerate(enriched_papers, 1):
        paper_titles[str(i)] = {
            'title': paper['title'],
            'score': paper.get('relevance_score', paper.get('score', 'N/A')),
            'categories': paper.get('ai_categories', []),
            'pdf_url': paper.get('pdf_url', '')
        }
    print(f"Built mapping for {len(paper_titles)} paper references")

    # First, try to load pre-generated synthesis from HTML/MD file
    base_dir = os.path.dirname(csv_file) or "."
    stem = os.path.splitext(os.path.basename(csv_file))[0]
    if stem.endswith('_papers'):
        stem = stem[:-7]

    html_candidates = []
    md_candidates = []

    if synthesis_file:
        html_candidates.append(synthesis_file)
        md_candidates.append(os.path.splitext(synthesis_file)[0] + '.md')

    html_candidates.extend(sorted(glob.glob(os.path.join(base_dir, f"{stem}_synthesis*.html"))))
    html_candidates.append(os.path.join(base_dir, 'conference_synthesis.html'))

    md_candidates.extend(sorted(glob.glob(os.path.join(base_dir, f"{stem}_synthesis*.md"))))
    md_candidates.append(os.path.join(base_dir, 'conference_synthesis.md'))

    def upgrade_paper_refs(html_content):
        """Upgrade old-format paper references to new format with clickable PDF links."""
        def make_paper_link(paper_id):
            """Create a paper link for a given paper ID."""
            if paper_id in paper_titles:
                info = paper_titles[paper_id]
                title = info['title'].replace('"', '&quot;').replace("'", '&#39;')
                score = info.get('score', 'N/A')
                categories = ', '.join(info.get('categories', []))
                pdf_url = info.get('pdf_url', '')

                pdf_attr = f' data-pdf-url="{pdf_url}"' if pdf_url else ''
                return f'<a class="paper-ref" href="{pdf_url}" target="_blank" data-paper-id="{paper_id}" data-title="{title}" data-score="{score}" data-categories="{categories}"{pdf_attr}>[Paper {paper_id}]</a>'
            return f'[Paper {paper_id}]'  # Return plain text if paper not found

        def replace_old_ref(match):
            paper_id = match.group(1)
            return make_paper_link(paper_id)

        def replace_multi_paper_ref(match):
            """Handle [Paper X, Paper Y, Paper Z] patterns."""
            content = match.group(1)
            # Extract all paper numbers
            paper_nums = re.findall(r'Paper (\d+)', content)
            if not paper_nums:
                return match.group(0)
            # Create links for each paper
            links = [make_paper_link(num) for num in paper_nums]
            return '[' + ', '.join(links) + ']'

        def replace_mixed_ref(match):
            """Handle [Paper X, Y, Z] patterns where only first has 'Paper' prefix."""
            content = match.group(1)
            # Extract all numbers (first one after "Paper", rest are just numbers)
            paper_nums = re.findall(r'\d+', content)
            if not paper_nums:
                return match.group(0)
            # Create links for each paper
            links = [make_paper_link(num) for num in paper_nums]
            return '[' + ', '.join(links) + ']'

        # First, handle old format: <span class="paper-ref" data-paper-id="X" data-tooltip="...">
        pattern = r'<span class="paper-ref" data-paper-id="(\d+)" data-tooltip="([^"]*)">\[Paper \d+\]</span>'
        html_content = re.sub(pattern, replace_old_ref, html_content)

        # Handle multi-paper brackets like [Paper 11, Paper 18, Paper 30]
        multi_pattern = r'\[(Paper \d+(?:,\s*Paper \d+)+)\]'
        html_content = re.sub(multi_pattern, replace_multi_paper_ref, html_content)

        # Handle mixed format like [Paper 2, 19, 24, 92] where only first has "Paper"
        mixed_pattern = r'\[(Paper \d+(?:,\s*\d+)+)\]'
        html_content = re.sub(mixed_pattern, replace_mixed_ref, html_content)

        # Handle "Papers" plural format like [Papers 13, 111, 179, 308]
        papers_plural_pattern = r'\[Papers (\d+(?:,\s*\d+)+)\]'
        html_content = re.sub(papers_plural_pattern, replace_mixed_ref, html_content)

        # Handle single [Paper X] in brackets
        single_pattern = r'\[Paper (\d+)\]'
        html_content = re.sub(single_pattern, lambda m: make_paper_link(m.group(1)), html_content)

        # Finally, handle unbracketed "Paper X" references (but not already converted ones)
        # Use negative lookbehind/lookahead to skip already converted refs
        unbracketed_pattern = r'(?<!data-paper-id=")(?<!">)(?<!\[)Paper (\d+)(?!\])'
        html_content = re.sub(unbracketed_pattern, lambda m: make_paper_link(m.group(1)), html_content)

        return html_content

    def load_html(path):
        nonlocal synthesis_text
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Upgrade old-format paper refs to new format with PDF links
                synthesis_text = upgrade_paper_refs(content)
                print(f"✓ Loaded synthesis from {path}")
                return True
        except Exception as e:
            print(f"⚠ Error loading HTML synthesis file {path}: {e}")
            return False

    def load_md(path):
        nonlocal synthesis_text
        try:
            with open(path, 'r', encoding='utf-8') as f:
                synthesis_content = f.read()
                if '---' in synthesis_content:
                    parts = synthesis_content.split('---')
                    if len(parts) >= 3:
                        synthesis_md = parts[1].strip()
                    else:
                        synthesis_md = synthesis_content
                else:
                    synthesis_md = synthesis_content

                synthesis_text = markdown_to_html(synthesis_md, paper_titles)
                print(f"✓ Loaded synthesis from {path} (old format - may have incorrect tooltips)")
                print(f"  ⚠ Regenerate synthesis with 'python synthesize_conference.py' for correct tooltips")
                return True
        except Exception as e:
            print(f"⚠ Error loading markdown synthesis file {path}: {e}")
            return False

    for path in html_candidates:
        if os.path.exists(path) and load_html(path):
            break
    else:
        for path in md_candidates:
            if os.path.exists(path) and load_md(path):
                break

    # Fallback: generate synthesis if not loaded and we have enriched papers
    if not synthesis_text and enriched_paper_count > 0 and generate_synthesis:
        print(f"Generating research synthesis from {enriched_paper_count} enriched papers...")
        result = generate_synthesis(papers, all_categories, conference_name=conference_title)
        if result and isinstance(result, tuple):
            synthesis_text, _ = result
        else:
            synthesis_text = result
    elif not synthesis_text and enriched_paper_count == 0:
        print("No enriched papers available for synthesis")

    # Use provided conference title or derive from filename (e.g., neurips2025 -> NEURIPS 2025)
    if not conference_title:
        conference_title = "Conference Papers"
        source_path = enriched_papers_file or csv_file
        if source_path:
            base_name = os.path.splitext(os.path.basename(source_path))[0]
            prefix = base_name.split('_')[0] if '_' in base_name else base_name
            match = re.match(r'([A-Za-z]+)(\d{4})?', prefix)
            if match:
                conf_code = match.group(1).upper()
                year = match.group(2) or ''
                conference_title = f"{conf_code} {year}".strip()

    page_title = f"{conference_title} - PaperAtlas"

    synthesis_block = synthesis_text if synthesis_text else "<p style='color: #888; font-style: italic;'>No synthesis available. Enriched papers are required to generate a synthesis.</p>"

    # Generate deterministic paper reference list
    if paper_titles:
        reference_list_html = generate_paper_reference_list(paper_titles)
        synthesis_block += reference_list_html

    synthesis_block = f"<div style=\"font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\">{synthesis_block}</div>"

    # Generate HTML with embedded data (placeholders substituted after definition)
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{PAGE_TITLE}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f4f6f9;
            color: #2c3e50;
            padding: 0;
            min-height: 100vh;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 20px;
        }

        header {
            background: linear-gradient(135deg, #1c3664 0%, #0a1f44 100%);
            padding: 40px 20px 50px;
            margin-bottom: 40px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        h1 {
            color: #ffffff;
            font-size: 2.8em;
            margin-bottom: 15px;
            font-weight: 600;
            letter-spacing: -0.5px;
        }

        .subtitle {
            color: #b8c5d6;
            font-size: 1.15em;
            font-weight: 400;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
            text-align: center;
            transition: all 0.3s ease;
            border: 1px solid #e8ecef;
        }

        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
        }

        .stat-value {
            font-size: 2.8em;
            font-weight: 700;
            color: #1c3664;
            margin: 10px 0;
        }

        .stat-label {
            color: #5d6d7e;
            font-size: 0.85em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }

        .chart-section {
            background: white;
            padding: 35px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
            margin-bottom: 30px;
            border: 1px solid #e8ecef;
        }

        .chart-section h2 {
            color: #1c3664;
            margin-bottom: 25px;
            font-size: 1.75em;
            font-weight: 600;
        }

        .chart-container {
            position: relative;
            height: 300px;
            margin-bottom: 20px;
        }

        .papers-section {
            background: white;
            padding: 35px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
            border: 1px solid #e8ecef;
        }

        .papers-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .papers-header h2 {
            color: #667eea;
            font-size: 1.8em;
        }

        .sort-controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .sort-controls label {
            color: #666;
            font-weight: 500;
        }

        select {
            padding: 10px 15px;
            border: 2px solid #667eea;
            border-radius: 8px;
            background: white;
            color: #333;
            font-size: 1em;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        select:hover {
            background: #f8f9ff;
        }

        #paperSearch:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.15);
        }

        #paperSearch::placeholder {
            color: #999;
        }

        .paper-card {
            background: #ffffff;
            padding: 24px;
            border-radius: 6px;
            margin-bottom: 16px;
            border-left: 4px solid #00c781;
            transition: all 0.2s ease;
            border: 1px solid #e8ecef;
            border-left: 4px solid #00c781;
        }

        .paper-card:hover {
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            border-left-color: #1c3664;
        }

        .paper-header {
            display: flex;
            justify-content: space-between;
            align-items: start;
            margin-bottom: 10px;
            gap: 15px;
        }

        .paper-title {
            font-size: 1.2em;
            font-weight: 600;
            color: #333;
            flex: 1;
        }

        .paper-score {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1em;
            min-width: 60px;
            text-align: center;
        }

        .paper-authors {
            color: #666;
            margin-bottom: 10px;
            font-size: 0.95em;
        }

        .paper-details {
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin-top: 10px;
            font-size: 0.9em;
        }

        .detail-item {
            display: flex;
            align-items: center;
            gap: 5px;
            color: #666;
        }

        .detail-item strong {
            color: #667eea;
        }

        .paper-stats {
            display: flex;
            gap: 15px;
            margin-top: 10px;
        }

        .stat-badge {
            background: white;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.85em;
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .stat-badge strong {
            color: #667eea;
        }

        .paper-link {
            margin-top: 10px;
        }

        .paper-link a {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.3s ease;
        }

        .paper-link a:hover {
            color: #764ba2;
            text-decoration: underline;
        }

        .tabs {
            background: white;
            border-radius: 20px;
            padding: 10px;
            margin-bottom: 30px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
            display: flex;
            gap: 10px;
        }

        .tab {
            flex: 1;
            padding: 16px 30px;
            background: transparent;
            border: none;
            border-bottom: 3px solid transparent;
            border-radius: 0;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            color: #5d6d7e;
        }

        .tab:hover {
            color: #1c3664;
            background: #f8f9fb;
        }

        .tab.active {
            background: transparent;
            color: #1c3664;
            border-bottom: 3px solid #00c781;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        .author-card {
            background: #ffffff;
            padding: 24px;
            border-radius: 6px;
            margin-bottom: 16px;
            border-left: 4px solid #00c781;
            transition: all 0.2s ease;
            border: 1px solid #e8ecef;
        }

        .author-card:hover {
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            border-left-color: #1c3664;
        }

        .author-header {
            display: flex;
            flex-direction: row;
            gap: 15px;
            margin-bottom: 15px;
            align-items: flex-start;
        }

        .author-photo {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            object-fit: cover;
            border: 3px solid #667eea;
            flex-shrink: 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .author-photo-placeholder {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2em;
            color: white;
            font-weight: 600;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .author-info {
            flex: 1;
            min-width: 0;
        }

        .author-name {
            font-size: 1.3em;
            font-weight: 600;
            color: #333;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .author-profile-link {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 4px 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 0.7em;
            font-weight: 500;
            transition: all 0.2s ease;
        }

        .author-profile-link:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }

        .author-affiliation {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }

        .affiliation-badge {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 500;
        }

        .role-badge {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 500;
        }

        .author-stats-badges {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .author-badge {
            background: white;
            padding: 6px 12px;
            border-radius: 15px;
            font-size: 0.85em;
            display: flex;
            align-items: center;
            gap: 5px;
            white-space: nowrap;
        }

        .pagination-btn {
            padding: 8px 16px;
            border: 1px solid #ddd;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.2s ease;
        }

        .pagination-btn:hover:not(:disabled) {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: transparent;
        }

        .pagination-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .pagination-btn.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: transparent;
            font-weight: 600;
        }

        .pagination-info {
            color: #666;
            font-size: 0.9em;
        }

        .category-pill {
            display: inline-block;
            padding: 6px 14px;
            margin: 4px;
            border-radius: 20px;
            font-size: 0.85em;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 2px solid #ddd;
            background: white;
            color: #555;
        }

        .category-pill:hover {
            border-color: #667eea;
            background: #f0f4ff;
        }

        .category-pill.selected {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: transparent;
        }

        .paper-category-badge {
            display: inline-block;
            padding: 4px 10px;
            margin: 2px 4px 2px 0;
            border-radius: 12px;
            font-size: 0.75em;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            font-weight: 500;
        }

        .paper-card {
            cursor: pointer;
        }

        .paper-card.expanded {
            background: #f8f9fa;
        }

        .paper-expandable {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }

        .paper-card.expanded .paper-expandable {
            max-height: 500px;
            padding-top: 15px;
        }

        .paper-key-info {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .paper-key-info h4 {
            margin: 0 0 8px 0;
            color: #667eea;
            font-size: 0.9em;
        }

        .paper-key-info p {
            margin: 0;
            color: #555;
            font-size: 0.9em;
            line-height: 1.5;
        }

        .view-details-btn {
            display: inline-block;
            padding: 8px 16px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            font-size: 0.9em;
            margin-top: 10px;
            transition: transform 0.2s ease;
        }

        .view-details-btn:hover {
            transform: translateY(-2px);
        }

        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            align-items: center;
            justify-content: center;
        }

        .modal.active {
            display: flex;
        }

        .modal-content {
            background: white;
            border-radius: 15px;
            padding: 30px;
            max-width: 800px;
            max-height: 90vh;
            overflow-y: auto;
            position: relative;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }

        .modal-close {
            position: absolute;
            top: 15px;
            right: 15px;
            font-size: 28px;
            cursor: pointer;
            color: #999;
            background: none;
            border: none;
            padding: 0;
            width: 32px;
            height: 32px;
            line-height: 28px;
            text-align: center;
        }

        .modal-close:hover {
            color: #333;
        }

        .modal-section {
            margin-bottom: 20px;
        }

        .modal-section h3 {
            color: #667eea;
            margin: 0 0 10px 0;
            font-size: 1.1em;
        }

        .modal-section p {
            color: #555;
            line-height: 1.6;
            margin: 0;
        }

        .author-badge strong {
            color: #764ba2;
        }

        .author-papers-list {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
        }

        .author-paper-item {
            padding: 8px 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .author-paper-score {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 4px 10px;
            border-radius: 12px;
            font-weight: bold;
            font-size: 0.9em;
            min-width: 40px;
            text-align: center;
        }

        .author-paper-title {
            flex: 1;
            color: #333;
            font-size: 0.95em;
        }

        @media (max-width: 768px) {
            h1 {
                font-size: 2em;
            }

            .stats-grid {
                grid-template-columns: 1fr;
            }

            .papers-header {
                flex-direction: column;
                align-items: stretch;
            }

            .sort-controls {
                flex-direction: column;
                width: 100%;
            }

            select {
                width: 100%;
            }

            .tabs {
                flex-direction: column;
            }

            .author-header {
                flex-direction: column;
                align-items: flex-start;
            }
        }

        /* Paper reference links with tooltips */
        .paper-ref {
            color: #00c781;
            font-weight: 600;
            cursor: pointer;
            position: relative;
            text-decoration: underline dotted;
            transition: all 0.2s ease;
        }

        a.paper-ref {
            cursor: pointer;
        }

        a.paper-ref[href=""] {
            pointer-events: none;
            cursor: help;
        }

        .paper-ref:hover {
            color: #1c3664;
        }

        .paper-ref-missing {
            color: #ff6b6b;
        }

        /* JavaScript-based tooltip container */
        .paper-tooltip {
            position: fixed;
            background: rgba(0, 0, 0, 0.95);
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            max-width: 350px;
            font-size: 0.85em;
            font-weight: normal;
            line-height: 1.5;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            z-index: 10000;
            pointer-events: none;
            text-align: left;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.2s ease, visibility 0.2s ease;
        }

        .paper-tooltip.visible {
            opacity: 1;
            visibility: visible;
        }

        .paper-tooltip .tooltip-title {
            font-weight: 600;
            margin-bottom: 8px;
            color: #fff;
        }

        .paper-tooltip .tooltip-meta {
            font-size: 0.9em;
            color: #aaa;
        }

        .paper-tooltip .tooltip-pdf {
            margin-top: 8px;
            font-size: 0.85em;
            color: #00c781;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{CONF_TITLE}</h1>
            <p class="subtitle">Your personalized conference guide powered by <a href="https://github.com/aldro61/PaperAtlas" target="_blank" style="color:#60a5fa;">PaperAtlas</a></p>
        </header>

        <div class="tabs">
            <button class="tab active" onclick="switchTab('papers')">📄 Papers</button>
            <button class="tab" onclick="switchTab('authors')">👥 Authors</button>
            <button class="tab" onclick="switchTab('synthesis')">🔬 Synthesis</button>
        </div>

        <div id="papersTab" class="tab-content active">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Papers</div>
                    <div class="stat-value" id="totalPapers">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Average Score</div>
                    <div class="stat-value" id="avgScore">-</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Top Score</div>
                    <div class="stat-value" id="topScore">-</div>
                </div>
            </div>

            <div class="chart-section">
                <h2>📊 Score Distribution</h2>
                <div class="chart-container">
                    <canvas id="scoreChart"></canvas>
                </div>
            </div>

            <div class="papers-section">
                <div class="papers-header">
                    <h2>📄 Your Papers</h2>
                    <div class="sort-controls">
                        <label for="sortBy">Sort by:</label>
                        <select id="sortBy">
                            <option value="score">Score (highest first)</option>
                            <option value="title">Title (A–Z)</option>
                        </select>
                    </div>
                </div>

                <div class="search-container" style="margin-bottom: 20px;">
                    <div style="position: relative;">
                        <input type="text" id="paperSearch" placeholder="Search papers by title, author, or keywords..."
                               style="width: 100%; padding: 14px 16px 14px 45px; border: 2px solid #e8ecef; border-radius: 10px;
                                      font-size: 1em; background: white; transition: border-color 0.3s, box-shadow 0.3s;">
                        <span style="position: absolute; left: 16px; top: 50%; transform: translateY(-50%); font-size: 1.2em; opacity: 0.5;">🔍</span>
                        <button id="clearSearch" onclick="clearSearchBox()"
                                style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
                                       background: none; border: none; font-size: 1.2em; cursor: pointer; opacity: 0.5; display: none;"
                                title="Clear search">✕</button>
                    </div>
                    <div id="searchResultsInfo" style="margin-top: 8px; font-size: 0.9em; color: #666; display: none;"></div>
                </div>

                <div id="categoryFilters" style="margin-bottom: 25px;"></div>

                <div id="papersList"></div>

                <div id="papersPagination" style="display: flex; justify-content: center; align-items: center; gap: 10px; margin-top: 30px;">
                </div>
            </div>
        </div>

        <div id="authorsTab" class="tab-content">
            <div class="papers-section">
                <div class="papers-header">
                    <h2>👥 Key Authors to Meet</h2>
                </div>
                <div style="background: #f8f9fa; padding: 15px; border-radius: 10px; margin-bottom: 20px; font-size: 0.95em; color: #555;">
                    <strong>Ranking by Research Alignment:</strong> Authors are ranked by their number of <strong>highly relevant papers (score ≥ ''' + str(HIGHLY_RELEVANT_THRESHOLD) + ''')</strong>.
                    Showing <strong>first, second, and last authors</strong> (primary contributors, key collaborators, and senior researchers) with at least <strong>1 highly relevant paper</strong> — these are the must-meet researchers whose work is most aligned with your interests.
                    <span style="opacity: 0.8;">(Focusing on these key positions helps prioritize important contributors)</span>
                </div>

                <div style="background: white; padding: 25px; border-radius: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 30px;">
                    <h3 style="margin-top: 0; margin-bottom: 20px; color: #333;">🏛️ Top Institutions</h3>
                    <canvas id="affiliationChart" style="max-height: 400px;"></canvas>
                </div>

                <div id="authorsList"></div>

                <div id="authorsPagination" style="display: flex; justify-content: center; align-items: center; gap: 10px; margin-top: 30px;">
                </div>
            </div>
        </div>

        <div id="synthesisTab" class="tab-content">
            <div class="papers-section">
                <div class="papers-header">
                    <h2>🔬 Research Synthesis</h2>
                </div>
                <div style="background: #f8f9fa; padding: 15px; border-radius: 10px; margin-bottom: 20px; font-size: 0.95em; color: #555;">
                    <strong>Critical Analysis:</strong> A synthesized overview of major trends, surprising findings, and impactful work across all papers.
                </div>

                <div id="synthesisContent" style="background: white; padding: 30px; border-radius: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); line-height: 1.8; max-width: 900px; margin: 0 auto;">
                    {SYNTHESIS_BLOCK}
                </div>
            </div>
        </div>
    </div>

    <!-- Modal for paper details -->
    <div id="paperModal" class="modal">
        <div class="modal-content">
            <button class="modal-close" onclick="closePaperModal()">✕</button>
            <div id="modalContent"></div>
        </div>
    </div>

    <script>
        // Configuration
        const HIGHLY_RELEVANT_THRESHOLD = ''' + str(HIGHLY_RELEVANT_THRESHOLD) + ''';

        // Embedded paper data
        const papers = ''' + json.dumps(papers, ensure_ascii=False) + ''';

        // Embedded author data
        const authors = ''' + json.dumps(author_stats, ensure_ascii=False) + ''';

        // Available categories
        const allCategories = ''' + json.dumps(all_categories, ensure_ascii=False) + ''';

        // Pagination state
        let currentAuthorsPage = 1;
        const authorsPerPage = 10;
        let currentPapersPage = 1;
        const papersPerPage = 20;

        // Search state
        let searchQuery = '';

        function displayStats() {
            const scores = papers.map(p => parseInt(p.score));
            const totalPapers = papers.length;
            const avgScore = (scores.reduce((a, b) => a + b, 0) / totalPapers).toFixed(1);
            const topScore = Math.max(...scores);

            document.getElementById('totalPapers').textContent = totalPapers;
            document.getElementById('avgScore').textContent = avgScore;
            document.getElementById('topScore').textContent = topScore;
        }

        function displayChart() {
            const scores = papers.map(p => parseInt(p.score));

            // Create histogram bins focused on the 50-100 range (5-point resolution)
            const bins = {};
            const binSize = 5;
            const minBound = 50;
            const maxBound = 100;
            for (let i = minBound; i <= maxBound; i += binSize) {
                bins[i] = 0;
            }

            scores.forEach(score => {
                const clamped = Math.max(minBound, Math.min(maxBound, score));
                const bin = Math.floor((clamped - minBound) / binSize) * binSize + minBound;
                bins[bin] = (bins[bin] || 0) + 1;
            });

            const ctx = document.getElementById('scoreChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: Object.keys(bins).map(b => `${b}-${Math.min(parseInt(b) + binSize - 1, maxBound)}`),
                    datasets: [{
                        label: 'Number of Papers',
                        data: Object.values(bins),
                        backgroundColor: 'rgba(102, 126, 234, 0.8)',
                        borderColor: 'rgba(102, 126, 234, 1)',
                        borderWidth: 2,
                        borderRadius: 8
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                precision: 0
                            }
                        }
                    }
                }
            });
        }

        let selectedCategories = new Set();

        function renderCategoryFilters() {
            const filtersDiv = document.getElementById('categoryFilters');
            if (!allCategories || allCategories.length === 0) {
                filtersDiv.style.display = 'none';
                return;
            }

            let html = '<div style="margin-bottom: 10px;"><strong>Filter by Category:</strong></div><div>';
            allCategories.forEach(category => {
                html += `<div class="category-pill" onclick="toggleCategory('${category.replace(/'/g, "\\'")}')">${category}</div>`;
            });
            html += '</div>';
            filtersDiv.innerHTML = html;
        }

        function toggleCategory(category) {
            if (selectedCategories.has(category)) {
                selectedCategories.delete(category);
            } else {
                selectedCategories.add(category);
            }

            // Update UI
            document.querySelectorAll('.category-pill').forEach(pill => {
                if (pill.textContent === category) {
                    pill.classList.toggle('selected');
                }
            });

            // Re-display papers with filter
            displayPapers(document.getElementById('sortBy').value, 1);
        }

        function togglePaperCard(index) {
            const card = document.querySelectorAll('.paper-card')[index];
            card.classList.toggle('expanded');
        }

        function openPaperModal(paperIndex, currentPapers) {
            const paper = currentPapers[paperIndex];
            const modal = document.getElementById('paperModal');
            const modalContent = document.getElementById('modalContent');

            let html = `
                <h2 style="margin-top: 0; color: #667eea;">${paper.title || 'Untitled'}</h2>
                ${paper.ai_categories && paper.ai_categories.length > 0 ? `
                    <div style="margin-bottom: 20px;">
                        ${paper.ai_categories.map(cat => `<span class="paper-category-badge">${cat}</span>`).join('')}
                    </div>
                ` : ''}
                ${paper.authors ? `<p><strong>Authors:</strong> ${paper.authors}</p>` : ''}
                <p><strong>Relevance Score:</strong> <span style="font-size: 1.2em; color: #667eea; font-weight: bold;">${paper.score}</span></p>
                ${paper.session_type ? `<p><strong>Session:</strong> ${paper.session_type}</p>` : ''}
                ${paper.session_location ? `<p><strong>Location:</strong> ${paper.session_location}</p>` : ''}

                ${paper.description ? `
                    <div style="margin-top: 25px;">
                        <h3 style="color: #667eea; margin-bottom: 10px;">📖 What is this paper about?</h3>
                        <p style="line-height: 1.6;">${paper.description}</p>
                    </div>
                ` : ''}

                ${paper.novelty ? `
                    <div style="margin-top: 25px; padding: 20px; background: linear-gradient(135deg, #fff5e6 0%, #ffe6f0 100%); border-radius: 10px; border-left: 4px solid #f59e0b;">
                        <h3 style="color: #d97706; margin-top: 0; margin-bottom: 10px;">💡 What Makes This Novel?</h3>
                        <p style="line-height: 1.6; margin-bottom: 0;">${paper.novelty}</p>
                    </div>
                ` : ''}

                ${paper.key_contribution ? `
                    <div style="margin-top: 25px;">
                        <h3 style="color: #667eea; margin-bottom: 10px;">🎯 Key Contribution</h3>
                        <p style="line-height: 1.6;">${paper.key_contribution}</p>
                    </div>
                ` : ''}

                ${paper.key_findings ? `
                    <div style="margin-top: 25px;">
                        <h3 style="color: #667eea; margin-bottom: 10px;">🔍 Key Findings</h3>
                        <p style="line-height: 1.6;">${paper.key_findings}</p>
                    </div>
                ` : ''}

                ${paper.pdf_url ? `
                    <div style="margin-top: 25px;">
                        <a href="${paper.pdf_url}" target="_blank" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: 600;">
                            📄 View Full PDF
                        </a>
                    </div>
                ` : ''}
            `;

            modalContent.innerHTML = html;
            modal.classList.add('active');
        }

        function closePaperModal() {
            document.getElementById('paperModal').classList.remove('active');
        }

        function displayPapers(sortBy = 'score', page = 1) {
            currentPapersPage = page;
            let sortedPapers = [...papers];

            // Filter by search query
            if (searchQuery.trim()) {
                const query = searchQuery.toLowerCase().trim();
                const queryTerms = query.split(/\s+/).filter(t => t.length > 0);

                sortedPapers = sortedPapers.filter(paper => {
                    const title = (paper.title || '').toLowerCase();
                    const authors = (paper.authors || '').toLowerCase();
                    const description = (paper.description || '').toLowerCase();
                    const keyFindings = (paper.key_findings || '').toLowerCase();
                    const novelty = (paper.novelty || '').toLowerCase();
                    const categories = (paper.ai_categories || []).join(' ').toLowerCase();
                    const session = (paper.session_name || paper.session_type || '').toLowerCase();

                    const searchableText = `${title} ${authors} ${description} ${keyFindings} ${novelty} ${categories} ${session}`;

                    // All query terms must match somewhere
                    return queryTerms.every(term => searchableText.includes(term));
                });
            }

            // Filter by selected categories
            if (selectedCategories.size > 0) {
                sortedPapers = sortedPapers.filter(paper => {
                    if (!paper.ai_categories || paper.ai_categories.length === 0) {
                        return false;
                    }
                    return paper.ai_categories.some(cat => selectedCategories.has(cat));
                });
            }

            // Update search results info
            const searchResultsInfo = document.getElementById('searchResultsInfo');
            if (searchQuery.trim()) {
                searchResultsInfo.style.display = 'block';
                searchResultsInfo.innerHTML = `Found <strong>${sortedPapers.length}</strong> paper${sortedPapers.length !== 1 ? 's' : ''} matching "<em>${searchQuery}</em>"`;
            } else {
                searchResultsInfo.style.display = 'none';
            }

            switch(sortBy) {
                case 'score':
                    sortedPapers.sort((a, b) => parseInt(b.score) - parseInt(a.score));
                    break;
                case 'title':
                    sortedPapers.sort((a, b) => a.title.localeCompare(b.title));
                    break;
            }

            const totalPapers = sortedPapers.length;
            const totalPages = Math.ceil(totalPapers / papersPerPage);
            const startIdx = (page - 1) * papersPerPage;
            const endIdx = startIdx + papersPerPage;
            const pagePapers = sortedPapers.slice(startIdx, endIdx);

            const papersList = document.getElementById('papersList');
            papersList.innerHTML = pagePapers.map((paper, idx) => `
                <div class="paper-card" onclick="togglePaperCard(${idx})">
                    <div class="paper-header">
                        <div class="paper-title">${paper.title || 'Untitled'}</div>
                        <div class="paper-score">${paper.score}</div>
                    </div>
                    ${paper.ai_categories && paper.ai_categories.length > 0 ? `
                        <div style="margin: 10px 0;">
                            ${paper.ai_categories.map(cat => `<span class="paper-category-badge">${cat}</span>`).join('')}
                        </div>
                    ` : ''}
                    ${paper.authors ? `<div class="paper-authors">👥 ${paper.authors}</div>` : ''}
                    <div class="paper-details">
                        ${paper.session_type ? `<div class="detail-item"><strong>Session:</strong> ${paper.session_type}</div>` : ''}
                        ${paper.session_location ? `<div class="detail-item"><strong>Location:</strong> ${paper.session_location}</div>` : ''}
                    </div>
                    <div class="paper-expandable">
                        ${paper.novelty ? `
                            <div class="paper-key-info" style="background: linear-gradient(135deg, #fff5e6 0%, #ffe6f0 100%); border-left: 3px solid #f59e0b;">
                                <strong style="color: #d97706;">💡 What's Novel:</strong>
                                <p style="margin: 8px 0; line-height: 1.5;">${paper.novelty.substring(0, 200)}${paper.novelty.length > 200 ? '...' : ''}</p>
                            </div>
                        ` : ''}
                        ${paper.key_contribution ? `
                            <div class="paper-key-info">
                                <strong style="color: #667eea;">🎯 Key Contribution:</strong>
                                <p style="margin: 8px 0; line-height: 1.5;">${paper.key_contribution.substring(0, 150)}${paper.key_contribution.length > 150 ? '...' : ''}</p>
                            </div>
                        ` : ''}
                        ${paper.key_findings ? `
                            <div class="paper-key-info">
                                <strong style="color: #667eea;">🔍 Key Findings:</strong>
                                <p style="margin: 8px 0; line-height: 1.5;">${paper.key_findings.substring(0, 150)}${paper.key_findings.length > 150 ? '...' : ''}</p>
                            </div>
                        ` : ''}
                        <button onclick="event.stopPropagation(); openPaperModal(${idx}, ${JSON.stringify(pagePapers).replace(/"/g, '&quot;')})"
                                style="margin-top: 15px; padding: 8px 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">
                            View Full Details
                        </button>
                    </div>

                    ${paper.pdf_url ? `<div class="paper-link"><a href="${paper.pdf_url}" target="_blank" onclick="event.stopPropagation()">📄 View PDF →</a></div>` : ''}
                </div>
            `).join('');

            // Render pagination controls
            const paginationDiv = document.getElementById('papersPagination');
            if (totalPages > 1) {
                let paginationHTML = '';

                // Previous button
                paginationHTML += `<button class="pagination-btn" onclick="displayPapers('${sortBy}', ${page - 1})" ${page === 1 ? 'disabled' : ''}>← Previous</button>`;

                // Page info
                paginationHTML += `<span class="pagination-info">Page ${page} of ${totalPages} (${totalPapers} papers)</span>`;

                // Next button
                paginationHTML += `<button class="pagination-btn" onclick="displayPapers('${sortBy}', ${page + 1})" ${page === totalPages ? 'disabled' : ''}>Next →</button>`;

                paginationDiv.innerHTML = paginationHTML;
            } else {
                paginationDiv.innerHTML = '';
            }

            // Scroll to top of papers list
            if (page > 1) {
                document.getElementById('papersList').scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }

        // Search box helper functions
        function clearSearchBox() {
            const searchInput = document.getElementById('paperSearch');
            searchInput.value = '';
            searchQuery = '';
            document.getElementById('clearSearch').style.display = 'none';
            displayPapers(document.getElementById('sortBy').value, 1);
        }

        let searchDebounceTimer = null;
        function handleSearchInput(e) {
            const clearBtn = document.getElementById('clearSearch');
            clearBtn.style.display = e.target.value ? 'block' : 'none';

            // Debounce search to avoid too many re-renders
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                searchQuery = e.target.value;
                displayPapers(document.getElementById('sortBy').value, 1);
            }, 200);
        }

        // Initialize on load
        document.addEventListener('DOMContentLoaded', () => {
            displayStats();
            displayChart();
            renderCategoryFilters();
            displayPapers();

            document.getElementById('sortBy').addEventListener('change', (e) => {
                displayPapers(e.target.value);
            });

            // Initialize search box
            const searchInput = document.getElementById('paperSearch');
            searchInput.addEventListener('input', handleSearchInput);
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    clearSearchBox();
                    searchInput.blur();
                }
            });

            // Initialize authors display
            displayAffiliationChart();
            displayAuthors();

            // Close modal when clicking outside
            document.getElementById('paperModal').addEventListener('click', (e) => {
                if (e.target.id === 'paperModal') {
                    closePaperModal();
                }
            });

            // Initialize paper reference tooltips
            initPaperTooltips();
        });

        // Paper reference tooltip system
        function initPaperTooltips() {
            // Create tooltip element
            const tooltip = document.createElement('div');
            tooltip.className = 'paper-tooltip';
            tooltip.id = 'paperTooltip';
            document.body.appendChild(tooltip);

            // Add event listeners to all paper references
            document.querySelectorAll('.paper-ref').forEach(ref => {
                ref.addEventListener('mouseenter', showPaperTooltip);
                ref.addEventListener('mouseleave', hidePaperTooltip);
                ref.addEventListener('mousemove', movePaperTooltip);
            });
        }

        function showPaperTooltip(e) {
            const ref = e.target;
            const tooltip = document.getElementById('paperTooltip');

            const title = ref.getAttribute('data-title');
            const score = ref.getAttribute('data-score');
            const categories = ref.getAttribute('data-categories');
            const pdfUrl = ref.getAttribute('data-pdf-url') || ref.getAttribute('href');
            const paperId = ref.getAttribute('data-paper-id');

            if (!title) {
                // Missing paper reference
                tooltip.innerHTML = `<div class="tooltip-title">⚠️ Paper ${paperId} not found in index</div>`;
            } else {
                let content = `<div class="tooltip-title">${title}</div>`;
                content += `<div class="tooltip-meta">Score: ${score}`;
                if (categories) {
                    content += ` | ${categories}`;
                }
                content += '</div>';
                if (pdfUrl && pdfUrl !== '') {
                    content += '<div class="tooltip-pdf">📄 Click to open PDF</div>';
                }
                tooltip.innerHTML = content;
            }

            // Position tooltip near mouse
            positionTooltip(e, tooltip);
            tooltip.classList.add('visible');
        }

        function hidePaperTooltip() {
            const tooltip = document.getElementById('paperTooltip');
            tooltip.classList.remove('visible');
        }

        function movePaperTooltip(e) {
            const tooltip = document.getElementById('paperTooltip');
            if (tooltip.classList.contains('visible')) {
                positionTooltip(e, tooltip);
            }
        }

        function positionTooltip(e, tooltip) {
            const padding = 15;
            let x = e.clientX + padding;
            let y = e.clientY - tooltip.offsetHeight - padding;

            // Keep tooltip within viewport
            const rect = tooltip.getBoundingClientRect();
            if (x + rect.width > window.innerWidth) {
                x = e.clientX - rect.width - padding;
            }
            if (y < 0) {
                y = e.clientY + padding;
            }

            tooltip.style.left = x + 'px';
            tooltip.style.top = y + 'px';
        }

        function switchTab(tabName) {
            // Hide all tabs
            document.getElementById('papersTab').classList.remove('active');
            document.getElementById('authorsTab').classList.remove('active');
            document.getElementById('synthesisTab').classList.remove('active');

            // Remove active from all tab buttons
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));

            // Show selected tab
            if (tabName === 'papers') {
                document.getElementById('papersTab').classList.add('active');
                document.querySelectorAll('.tab')[0].classList.add('active');
            } else if (tabName === 'authors') {
                document.getElementById('authorsTab').classList.add('active');
                document.querySelectorAll('.tab')[1].classList.add('active');
            } else if (tabName === 'synthesis') {
                document.getElementById('synthesisTab').classList.add('active');
                document.querySelectorAll('.tab')[2].classList.add('active');
            }
        }

        function displayAffiliationChart() {
            // Get authors with highly relevant papers and known affiliations
            const qualifyingAuthors = authors.filter(a =>
                a.highly_relevant_count >= 1 &&
                a.affiliation &&
                a.affiliation !== 'Unknown'
            );

            // Count affiliations
            const affiliationCounts = {};
            qualifyingAuthors.forEach(author => {
                const affiliation = author.affiliation;
                affiliationCounts[affiliation] = (affiliationCounts[affiliation] || 0) + 1;
            });

            // Sort by count and take top 15
            const sortedAffiliations = Object.entries(affiliationCounts)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 15);

            const labels = sortedAffiliations.map(a => a[0]);
            const data = sortedAffiliations.map(a => a[1]);

            const ctx = document.getElementById('affiliationChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Number of Researchers',
                        data: data,
                        backgroundColor: 'rgba(102, 126, 234, 0.8)',
                        borderColor: 'rgba(102, 126, 234, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        title: {
                            display: true,
                            text: `Top Institutions (${qualifyingAuthors.length} of ${authors.filter(a => a.highly_relevant_count >= 1).length} authors have known affiliations)`,
                            font: {
                                size: 13
                            },
                            color: '#666'
                        }
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            },
                            title: {
                                display: true,
                                text: 'Number of Researchers'
                            }
                        }
                    }
                }
            });
        }

        function displayAuthors(page = 1) {
            currentAuthorsPage = page;

            // Filter to authors with at least 1 highly relevant paper
            let sortedAuthors = authors
                .filter(a => a.highly_relevant_count >= 1)
                .map(a => ({
                    ...a,
                    papers: (a.papers || []).slice().sort((p1, p2) => {
                        const s1 = parseFloat(p1.score || 0);
                        const s2 = parseFloat(p2.score || 0);
                        if (s1 !== s2) return s2 - s1;
                        return (p1.title || '').localeCompare(p2.title || '');
                    })
                }))
                .sort((a, b) => {
                    if (b.highly_relevant_count !== a.highly_relevant_count) {
                        return b.highly_relevant_count - a.highly_relevant_count;
                    }
                    const avgA = parseFloat(a.avg_score || 0);
                    const avgB = parseFloat(b.avg_score || 0);
                    if (avgB !== avgA) {
                        return avgB - avgA;
                    }
                    return (a.name || '').localeCompare(b.name || '');
                });

            const totalAuthors = sortedAuthors.length;
            const totalPages = Math.ceil(totalAuthors / authorsPerPage);
            const startIdx = (page - 1) * authorsPerPage;
            const endIdx = startIdx + authorsPerPage;
            const pageAuthors = sortedAuthors.slice(startIdx, endIdx);

            const authorsList = document.getElementById('authorsList');
            authorsList.innerHTML = pageAuthors.map(author => `
                <div class="author-card">
                    <div class="author-header">
                        ${author.photo_url ? `
                            <img src="${author.photo_url}" alt="${author.name}" class="author-photo" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                            <div class="author-photo-placeholder" style="display: none;">${author.name.charAt(0)}</div>
                        ` : `
                            <div class="author-photo-placeholder">${author.name.charAt(0)}</div>
                        `}
                        <div class="author-info">
                            <div class="author-name">
                                ${author.name}
                                ${author.profile_url ? `<a href="${author.profile_url}" target="_blank" class="author-profile-link" onclick="event.stopPropagation()">🔗 Profile</a>` : ''}
                            </div>
                            ${author.affiliation && author.affiliation !== 'Unknown' ? `
                                <div class="author-affiliation">
                                    <span class="affiliation-badge" title="Current affiliation">${author.affiliation}</span>
                                    ${author.role && author.role !== 'Unknown' ? `<span class="role-badge" title="Academic/professional role">${author.role}</span>` : ''}
                                </div>
                            ` : ''}
                            <div class="author-stats-badges">
                                <div class="author-badge" title="Total number of papers by this author that align with your interests">
                                    📄 <strong>${author.paper_count}</strong> total
                                </div>
                                <div class="author-badge" title="Average relevance score across all their papers (higher = better alignment with your interests)">
                                    📊 <strong>${author.avg_score}</strong> avg
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="author-papers-list">
                        ${author.papers.map(paper => `
                            <div class="author-paper-item">
                                <div class="author-paper-score" title="Relevance score: how well this paper aligns with your research interests (higher = stronger alignment)">${paper.score}</div>
                                <div class="author-paper-title">${paper.title}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('');

            // Render pagination controls
            const paginationDiv = document.getElementById('authorsPagination');
            if (totalPages > 1) {
                let paginationHTML = '';

                // Previous button
                paginationHTML += `<button class="pagination-btn" onclick="displayAuthors(${page - 1})" ${page === 1 ? 'disabled' : ''}>← Previous</button>`;

                // Page info
                paginationHTML += `<span class="pagination-info">Page ${page} of ${totalPages} (${totalAuthors} authors)</span>`;

                // Next button
                paginationHTML += `<button class="pagination-btn" onclick="displayAuthors(${page + 1})" ${page === totalPages ? 'disabled' : ''}>Next →</button>`;

                paginationDiv.innerHTML = paginationHTML;
            } else {
                paginationDiv.innerHTML = '';
            }

            // Scroll to top of authors list
            if (page > 1) {
                document.getElementById('authorsList').scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
    </script>
</body>
</html>'''

    # Substitute dynamic conference metadata
    html = html.replace("{PAGE_TITLE}", page_title).replace("{CONF_TITLE}", conference_title).replace("{SYNTHESIS_BLOCK}", synthesis_block)

    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated website: {output_file}")
    print(f"Open it in your browser to view your papers!")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Generate HTML website from conference data')
    parser.add_argument('--csv', required=True, help='Path to papers CSV file')
    parser.add_argument('--papers', required=True, help='Path to enriched papers JSON file')
    parser.add_argument('--authors', required=True, help='Path to enriched authors JSON file')
    parser.add_argument('--synthesis', help='Path to synthesis HTML file')
    parser.add_argument('--output', '-o', required=True, help='Output HTML file path')

    args = parser.parse_args()

    print(f"Input files:")
    print(f"  CSV: {args.csv}")
    print(f"  Enriched papers: {args.papers}")
    print(f"  Enriched authors: {args.authors}")
    print(f"  Synthesis: {args.synthesis or 'none'}")
    print(f"Output: {args.output}")
    print()

    generate_website(args.csv, args.output, args.authors, args.papers, synthesis_file=args.synthesis)
