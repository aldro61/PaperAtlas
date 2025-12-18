#!/usr/bin/env python3
"""
Shared utility functions for PaperAtlas.
"""

from collections import defaultdict

from config import HIGHLY_RELEVANT_THRESHOLD


def parse_authors(author_string):
    """Parse author string into individual authors.

    Args:
        author_string: Comma-separated string of author names

    Returns:
        List of cleaned author names
    """
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
        papers: List of papers to analyze. Each paper should have at minimum:
            - 'authors': comma-separated author string
            - 'title': paper title
            - 'relevance_score' or 'score': relevance score
            Optional fields that will be included if present:
            - 'session_type' or 'session_name': session information
            - 'pdf_url': link to PDF
            - 'relevant_to_users' or 'liked': engagement metric
            - 'read_by_users': read count metric
        first_last_only: If True, only consider first, second, and last authors (default: True)

    Returns:
        List of author statistics dictionaries, each containing:
            - 'name': author name
            - 'paper_count': number of papers
            - 'highly_relevant_count': papers with score >= HIGHLY_RELEVANT_THRESHOLD
            - 'avg_score': average relevance score
            - 'max_score': maximum relevance score
            - 'total_relevant': sum of relevant/liked counts
            - 'total_reads': sum of read counts
            - 'papers': list of paper info dicts
    """
    author_papers = defaultdict(list)
    author_scores = defaultdict(list)
    author_engagement = defaultdict(lambda: {'relevant': 0, 'reads': 0})

    for paper in papers:
        authors = parse_authors(paper.get('authors', ''))

        # Handle both old format (0-100) and new format (already percentage)
        score_raw = paper.get('relevance_score', paper.get('score', 0))
        try:
            score = float(score_raw)
        except (ValueError, TypeError):
            score = 0.0

        # For engagement metrics, use available fields or defaults
        relevant_raw = paper.get('relevant_to_users', paper.get('liked', 0))
        if isinstance(relevant_raw, str):
            relevant = 1 if relevant_raw.lower() in {"true", "1", "yes", "y"} else 0
        else:
            try:
                relevant = int(bool(relevant_raw))
            except (ValueError, TypeError):
                relevant = 0

        reads_raw = paper.get('read_by_users', 0)
        try:
            reads = int(reads_raw)
        except (ValueError, TypeError):
            reads = 0

        # Filter to first, second, and last authors if enabled
        if first_last_only and len(authors) > 3:
            # Keep first, second, and last author
            authors = [authors[0], authors[1], authors[-1]]
        # If <= 3 authors or first_last_only=False, keep all

        for author in authors:
            # Build paper info dict with all available fields
            paper_info = {
                'title': paper.get('title', ''),
                'score': score,
            }
            # Include optional fields if present
            session = paper.get('session_type', paper.get('session_name', ''))
            if session:
                paper_info['session'] = session
            if paper.get('pdf_url'):
                paper_info['pdf_url'] = paper['pdf_url']
            paper_info['relevant'] = relevant
            paper_info['reads'] = reads

            author_papers[author].append(paper_info)
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

        # Count highly relevant papers (strong alignment with user's interests)
        highly_relevant_count = sum(1 for score in author_scores[author] if score >= HIGHLY_RELEVANT_THRESHOLD)

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
