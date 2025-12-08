#!/usr/bin/env python3
"""
Generate an HTML website with embedded paper data.
"""

import csv
import json
import os
import sys

# Import synthesis generation
sys.path.append(os.path.dirname(__file__))
try:
    from synthesize_conference import generate_synthesis
except ImportError:
    generate_synthesis = None

def markdown_to_html(text, paper_titles=None):
    """Convert basic markdown to HTML with interactive paper references.

    Args:
        text: Markdown text to convert
        paper_titles: Optional dict mapping paper number to {title, score, categories}
    """
    import re

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

    # Convert paper references [Paper X] to interactive tooltips
    if paper_titles:
        def replace_paper_ref(match):
            paper_num = match.group(1)
            if paper_num in paper_titles:
                info = paper_titles[paper_num]
                title = info['title'].replace('"', '&quot;').replace("'", '&#39;')
                score = info.get('score', 'N/A')
                categories = ', '.join(info.get('categories', []))

                tooltip_html = f"{title}<br><small style='color: #888;'>Score: {score} | {categories}</small>"

                return f'<span class="paper-ref" data-tooltip="{tooltip_html}">[Paper {paper_num}]</span>'
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

def parse_authors(author_string):
    """Parse author string into individual authors."""
    if not author_string:
        return []

    # Split by comma
    authors = [a.strip() for a in author_string.split(',')]

    # Clean up common patterns
    cleaned = []
    for author in authors:
        # Remove "..." or "et al" type endings
        if author in ['...', 'et al', 'et al.']:
            continue
        # Remove trailing dots
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
    from collections import defaultdict

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
                'score': score,
                'session': paper['session_type'],
                'pdf_url': paper['pdf_url'],
                'relevant': relevant,
                'reads': reads
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

        # Count highly relevant papers (score >= 85 - strong alignment with your interests)
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

def generate_website(csv_file, output_file, enriched_authors_file=None, enriched_papers_file=None):
    """Generate HTML website with embedded data from CSV."""

    # Read CSV data
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        papers = list(reader)

    print(f"Loaded {len(papers)} papers from CSV")

    # Load enriched paper data if available
    all_categories = []
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

    # Merge enriched data with papers
    for paper in papers:
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

    # Analyze authors
    print("Analyzing authors...")
    author_stats = analyze_authors(papers)
    print(f"Found {len(author_stats)} unique authors")

    # Load enriched author data if available
    enriched_data = {}
    if enriched_authors_file:
        try:
            with open(enriched_authors_file, 'r', encoding='utf-8') as f:
                enriched_authors = json.load(f)
                # Create a lookup dict by author name
                for author in enriched_authors:
                    enriched_data[author['name']] = {
                        'affiliation': author.get('affiliation', 'Unknown'),
                        'role': author.get('role', 'Unknown'),
                        'photo_url': author.get('photo_url', None),
                        'profile_url': author.get('profile_url', None)
                    }
                print(f"Loaded enriched data for {len(enriched_data)} authors")
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

    # Load or generate synthesis if we have enriched papers
    synthesis_text = None
    enriched_paper_count = sum(1 for p in papers if p.get('key_findings'))

    # Build paper titles mapping for interactive tooltips
    paper_titles = {}
    enriched_papers = [p for p in papers if p.get('key_findings') and p.get('novelty')]
    for i, paper in enumerate(enriched_papers, 1):
        paper_titles[str(i)] = {
            'title': paper['title'],
            'score': paper.get('score', 'N/A'),
            'categories': paper.get('ai_categories', [])
        }
    print(f"Built mapping for {len(paper_titles)} paper references")

    # First, try to load pre-generated synthesis from HTML file (new format)
    synthesis_html_file = os.path.join(os.path.dirname(csv_file), 'conference_synthesis.html')
    synthesis_md_file = os.path.join(os.path.dirname(csv_file), 'conference_synthesis.md')

    if os.path.exists(synthesis_html_file):
        try:
            with open(synthesis_html_file, 'r', encoding='utf-8') as f:
                synthesis_text = f.read()
                print(f"✓ Loaded synthesis from {synthesis_html_file} (with correct tooltips)")
        except Exception as e:
            print(f"⚠ Error loading HTML synthesis file: {e}")
    elif os.path.exists(synthesis_md_file):
        # Backwards compatibility with old markdown format
        try:
            with open(synthesis_md_file, 'r', encoding='utf-8') as f:
                synthesis_content = f.read()
                # Extract the main content (skip the header and reference index)
                if '---' in synthesis_content:
                    parts = synthesis_content.split('---')
                    if len(parts) >= 3:
                        # Get the middle part (between the two --- markers)
                        synthesis_md = parts[1].strip()
                    else:
                        synthesis_md = synthesis_content
                else:
                    synthesis_md = synthesis_content

                # Convert markdown to HTML with interactive paper references
                synthesis_text = markdown_to_html(synthesis_md, paper_titles)
                print(f"✓ Loaded synthesis from {synthesis_md_file} (old format - may have incorrect tooltips)")
                print(f"  ⚠ Regenerate synthesis with 'python synthesize_conference.py' for correct tooltips")
        except Exception as e:
            print(f"⚠ Error loading markdown synthesis file: {e}")

    # Fallback: generate synthesis if not loaded and we have enriched papers
    if not synthesis_text and enriched_paper_count > 0 and generate_synthesis and all_categories:
        print(f"Generating research synthesis from {enriched_paper_count} enriched papers...")
        result = generate_synthesis(papers, all_categories)
        if result and isinstance(result, tuple):
            synthesis_text, _ = result
        else:
            synthesis_text = result
    elif not synthesis_text and enriched_paper_count == 0:
        print("No enriched papers available for synthesis")

    # Generate HTML with embedded data
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conference Papers - PaperAtlas</title>
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
            padding: 60px 20px;
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

        /* Paper reference tooltips */
        .paper-ref {
            color: #00c781;
            font-weight: 600;
            cursor: help;
            position: relative;
            text-decoration: underline dotted;
            transition: all 0.2s ease;
        }

        .paper-ref:hover {
            color: #1c3664;
        }

        .paper-ref::after {
            content: attr(data-tooltip);
            position: absolute;
            bottom: 125%;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 0, 0, 0.95);
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            white-space: normal;
            width: 320px;
            font-size: 0.85em;
            font-weight: normal;
            line-height: 1.5;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            z-index: 1000;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s ease, visibility 0.3s ease;
            pointer-events: none;
            text-align: left;
        }

        .paper-ref:hover::after {
            opacity: 1;
            visibility: visible;
        }

        /* Tooltip arrow */
        .paper-ref::before {
            content: '';
            position: absolute;
            bottom: 115%;
            left: 50%;
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: rgba(0, 0, 0, 0.95);
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s ease, visibility 0.3s ease;
        }

        .paper-ref:hover::before {
            opacity: 1;
            visibility: visible;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎓 Conference Papers</h1>
            <p class="subtitle">Your personalized conference guide</p>
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
                <div class="stat-card">
                    <div class="stat-label">Most Popular</div>
                    <div class="stat-value" id="mostPopular">-</div>
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
                            <option value="relevant">Most Relevant</option>
                            <option value="reads">Most Read</option>
                            <option value="title">Title (A-Z)</option>
                        </select>
                    </div>
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
                    <strong>Ranking by Research Alignment:</strong> Authors are ranked by their number of <strong>highly relevant papers (score ≥ 85)</strong>.
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
                    ''' + (f'<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif;">{synthesis_text if synthesis_text else "<p style=\'color: #888; font-style: italic;\'>No synthesis available. Enriched papers are required to generate a synthesis.</p>"}</div>' if True else '') + '''
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

        function displayStats() {
            const scores = papers.map(p => parseInt(p.score));
            const totalPapers = papers.length;
            const avgScore = (scores.reduce((a, b) => a + b, 0) / totalPapers).toFixed(1);
            const topScore = Math.max(...scores);

            // Find most popular paper (by relevant_to_users)
            const mostPopular = papers.reduce((max, p) => {
                const relevant = parseInt(p.relevant_to_users) || 0;
                const maxRelevant = parseInt(max.relevant_to_users) || 0;
                return relevant > maxRelevant ? p : max;
            }, papers[0]);

            document.getElementById('totalPapers').textContent = totalPapers;
            document.getElementById('avgScore').textContent = avgScore;
            document.getElementById('topScore').textContent = topScore;
            document.getElementById('mostPopular').textContent = `${parseInt(mostPopular.relevant_to_users) || 0} 👍`;
        }

        function displayChart() {
            const scores = papers.map(p => parseInt(p.score));

            // Create histogram bins
            const bins = {};
            const binSize = 10;
            for (let i = 0; i < 100; i += binSize) {
                bins[i] = 0;
            }

            scores.forEach(score => {
                const bin = Math.floor(score / binSize) * binSize;
                bins[bin] = (bins[bin] || 0) + 1;
            });

            const ctx = document.getElementById('scoreChart').getContext('2d');
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: Object.keys(bins).map(b => `${b}-${parseInt(b) + binSize - 1}`),
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

                <div style="margin-top: 30px;">
                    ${paper.relevant_to_users ? `<span style="margin-right: 15px;">👍 <strong>${paper.relevant_to_users}</strong> found relevant</span>` : ''}
                    ${paper.read_by_users ? `<span>📖 <strong>${paper.read_by_users}</strong> reads</span>` : ''}
                </div>

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

            // Filter by selected categories
            if (selectedCategories.size > 0) {
                sortedPapers = sortedPapers.filter(paper => {
                    if (!paper.ai_categories || paper.ai_categories.length === 0) {
                        return false;
                    }
                    return paper.ai_categories.some(cat => selectedCategories.has(cat));
                });
            }

            switch(sortBy) {
                case 'score':
                    sortedPapers.sort((a, b) => parseInt(b.score) - parseInt(a.score));
                    break;
                case 'relevant':
                    sortedPapers.sort((a, b) => (parseInt(b.relevant_to_users) || 0) - (parseInt(a.relevant_to_users) || 0));
                    break;
                case 'reads':
                    sortedPapers.sort((a, b) => (parseInt(b.read_by_users) || 0) - (parseInt(a.read_by_users) || 0));
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
                    <div class="paper-stats">
                        ${paper.relevant_to_users ? `<div class="stat-badge">👍 <strong>${paper.relevant_to_users}</strong> found relevant</div>` : ''}
                        ${paper.read_by_users ? `<div class="stat-badge">📖 <strong>${paper.read_by_users}</strong> reads</div>` : ''}
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

        // Initialize on load
        document.addEventListener('DOMContentLoaded', () => {
            displayStats();
            displayChart();
            renderCategoryFilters();
            displayPapers();

            document.getElementById('sortBy').addEventListener('change', (e) => {
                displayPapers(e.target.value);
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
        });

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

            // Filter to authors with at least 1 highly relevant paper (score >= 85)
            let sortedAuthors = authors
                .filter(a => a.highly_relevant_count >= 1)
                .sort((a, b) => {
                    // Sort by highly relevant count first, then total papers as tiebreaker
                    if (b.highly_relevant_count !== a.highly_relevant_count) {
                        return b.highly_relevant_count - a.highly_relevant_count;
                    }
                    return b.paper_count - a.paper_count;
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
                                ${author.total_relevant > 0 ? `<div class="author-badge" title="Total times their papers were marked relevant by other users">👍 <strong>${author.total_relevant}</strong></div>` : ''}
                                ${author.total_reads > 0 ? `<div class="author-badge" title="Total times their papers were read by other users">📖 <strong>${author.total_reads}</strong></div>` : ''}
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

    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated website: {output_file}")
    print(f"Open it in your browser to view your papers!")

if __name__ == "__main__":
    csv_file = "papers.csv"
    output_file = "index.html"
    enriched_authors_file = "enriched_authors.json"
    enriched_papers_file = "enriched_papers.json"

    generate_website(csv_file, output_file, enriched_authors_file, enriched_papers_file)
