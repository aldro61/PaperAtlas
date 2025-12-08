#!/usr/bin/env python3
"""
Extract papers with positive scores from Scholar Inbox MHTML file using BeautifulSoup.
"""

import re
import csv
import quopri
from bs4 import BeautifulSoup

def extract_html_from_mhtml(file_path):
    """Extract HTML content from MHTML file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the HTML section (after Content-Type: text/html)
    html_match = re.search(r'Content-Type: text/html.*?Content-Location:.*?\n\n(.*?)(?=\n------MultipartBoundary)',
                          content, re.DOTALL)

    if not html_match:
        # Try alternative pattern
        html_match = re.search(r'<!DOCTYPE html>.*', content, re.DOTALL)

    if html_match:
        html_content = html_match.group(0) if html_match.group(0).startswith('<!DOCTYPE') else html_match.group(1)

        # Decode quoted-printable encoding
        # Replace =\n with nothing (soft line breaks)
        html_content = re.sub(r'=\r?\n', '', html_content)
        # Decode =XX sequences
        html_content = re.sub(r'=([0-9A-F]{2})', lambda m: chr(int(m.group(1), 16)), html_content)

        return html_content

    return content

def extract_papers_from_html(html_content):
    """Extract papers with positive scores from HTML."""

    soup = BeautifulSoup(html_content, 'html.parser')
    papers = []

    # Find all paper divs with id="paper{number}"
    paper_divs = soup.find_all('div', id=re.compile(r'^paper\d+$'))

    print(f"Found {len(paper_divs)} paper sections")

    for paper_div in paper_divs:
        try:
            # Get paper ID from the div id attribute
            paper_id = paper_div.get('id', '').replace('paper', '')
            if not paper_id:
                continue

            # Find score - look for aria-label="Paper Relevance"
            score_elem = paper_div.find('p', {'aria-label': 'Paper Relevance'})
            if not score_elem:
                continue

            try:
                score = int(score_elem.get_text().strip())
            except ValueError:
                continue

            # Only process papers with positive scores
            if score <= 0:
                continue

            # Extract title - look for h6 with subtitle1 class
            title = ""
            title_elem = paper_div.find('h6', class_=re.compile(r'.*subtitle1.*'))
            if title_elem:
                title = title_elem.get_text().strip()

            # Extract authors - look for p tag with body1 class in the author section
            authors = ""
            # The authors are typically in a <p> tag after the title
            author_elem = paper_div.find('p', class_=re.compile(r'.*body1.*'))
            if author_elem:
                authors = author_elem.get_text().strip()

            # Extract session information
            session_type = ""
            session_time = ""
            session_location = ""

            # Look for session spans
            session_spans = paper_div.find_all('span')
            for span in session_spans:
                span_text = span.get_text().strip()
                # Session type patterns: "SD-1-3606", "Oral 1A", etc.
                if re.match(r'^(SD-\d+-\d+|Oral \w+|Poster .+)$', span_text):
                    session_type = span_text
                    break

            # Look for time (format: HH:MM) near AccessTimeFilledIcon
            # The time is directly after the AccessTimeFilledIcon svg, before LocationOnIcon
            time_svg = paper_div.find('svg', {'data-testid': 'AccessTimeFilledIcon'})
            if time_svg:
                # Get the next sibling text (the time is between two svgs)
                next_text = time_svg.next_sibling
                if next_text and isinstance(next_text, str):
                    time_match = re.search(r'(\d{1,2}:\d{2})', next_text)
                    if time_match:
                        session_time = time_match.group(1)
                else:
                    # Try getting all text from parent span
                    parent_span = time_svg.find_parent('span')
                    if parent_span:
                        span_text = parent_span.get_text()
                        time_match = re.search(r'(\d{1,2}:\d{2})', span_text)
                        if time_match:
                            session_time = time_match.group(1)

            # Extract location - look for text after LocationOnIcon
            # This is tricky, but it's typically after an svg with LocationOnIcon
            location_svg = paper_div.find('svg', {'data-testid': 'LocationOnIcon'})
            if location_svg:
                # Get the next text after the svg
                next_elem = location_svg.find_next_sibling(string=True)
                if next_elem:
                    session_location = next_elem.strip()
                else:
                    # Try to find parent span and get text
                    parent = location_svg.parent
                    if parent:
                        location_text = parent.get_text().strip()
                        # Remove time if present
                        location_text = time_pattern.sub('', location_text).strip()
                        session_location = location_text

            # Extract PDF URL
            pdf_url = ""
            pdf_link = paper_div.find('a', href=re.compile(r'https://(arxiv\.org|openreview\.net)/pdf/'))
            if pdf_link:
                pdf_url = pdf_link.get('href', '')

            # Extract statistics
            relevant_to_users = ""
            reads = ""

            # Look for "Relevant to X users"
            relevant_elem = paper_div.find(attrs={'aria-label': re.compile(r'Relevant to \d+ users')})
            if relevant_elem:
                match = re.search(r'Relevant to (\d+) users', relevant_elem.get('aria-label', ''))
                if match:
                    relevant_to_users = match.group(1)

            # Look for "Read by X users"
            read_elem = paper_div.find(attrs={'aria-label': re.compile(r'Read by \d+ users')})
            if read_elem:
                match = re.search(r'Read by (\d+) users', read_elem.get('aria-label', ''))
                if match:
                    reads = match.group(1)

            paper = {
                'paper_id': paper_id,
                'score': score,
                'title': title,
                'authors': authors,
                'session_type': session_type,
                'session_time': session_time,
                'session_location': session_location,
                'pdf_url': pdf_url,
                'relevant_to_users': relevant_to_users,
                'read_by_users': reads
            }

            papers.append(paper)

        except Exception as e:
            print(f"Error processing paper {paper_id}: {e}")
            continue

    return papers

def deduplicate_papers(papers):
    """Remove duplicate papers, keeping poster sessions over oral sessions."""
    from collections import defaultdict

    print(f"\nDeduplicating papers...")
    print(f"  Papers before deduplication: {len(papers)}")

    # Group papers by title (or PDF URL as backup)
    paper_groups = defaultdict(list)
    for paper in papers:
        # Use title as primary key, fallback to PDF URL if no title
        key = paper['title'] if paper['title'] else paper['pdf_url']
        paper_groups[key].append(paper)

    # For each group, keep only one paper (preferring poster sessions)
    deduplicated = []
    duplicates_removed = 0

    for key, group in paper_groups.items():
        if len(group) == 1:
            # No duplicates
            deduplicated.append(group[0])
        else:
            # Found duplicates - prefer poster session (SD-X-XXXX format)
            poster_sessions = [p for p in group if p['session_type'].startswith('SD-')]
            oral_sessions = [p for p in group if p['session_type'].startswith('Oral')]

            if poster_sessions:
                # Keep the poster session
                kept = poster_sessions[0]
                deduplicated.append(kept)
                duplicates_removed += len(group) - 1
            elif oral_sessions:
                # No poster, keep first oral
                kept = oral_sessions[0]
                deduplicated.append(kept)
                duplicates_removed += len(group) - 1
            else:
                # Just keep first
                deduplicated.append(group[0])
                duplicates_removed += len(group) - 1

    print(f"  Papers after deduplication: {len(deduplicated)}")
    print(f"  Duplicates removed: {duplicates_removed}")

    return deduplicated

def write_papers_to_csv(papers, output_file):
    """Write papers to CSV file."""

    if not papers:
        print("No papers with positive scores found!")
        return

    fieldnames = ['paper_id', 'score', 'title', 'authors', 'session_type',
                  'session_time', 'session_location', 'pdf_url',
                  'relevant_to_users', 'read_by_users']

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(papers)

    print(f"\nExtracted {len(papers)} unique papers with positive scores to {output_file}")

if __name__ == "__main__":
    input_file = "conference.mhtml"
    output_file = "papers.csv"

    print("Extracting HTML from MHTML file...")
    html_content = extract_html_from_mhtml(input_file)

    print("Parsing HTML and extracting papers...")
    papers = extract_papers_from_html(html_content)

    # Deduplicate papers (prefer poster sessions over oral)
    papers = deduplicate_papers(papers)

    # Sort by score (highest first)
    papers.sort(key=lambda x: x['score'], reverse=True)

    write_papers_to_csv(papers, output_file)

    # Print summary
    print(f"\nSummary:")
    print(f"  Total papers: {len(papers)}")
    if papers:
        print(f"  Score range: {min(p['score'] for p in papers)} to {max(p['score'] for p in papers)}")
        print(f"  Average score: {sum(p['score'] for p in papers) / len(papers):.1f}")
