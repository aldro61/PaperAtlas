#!/usr/bin/env python3
"""
Generate a high-level critical summary of the conference research.
"""

import json
import os
import re
import sys

from openai import OpenAI

# Pre-compiled regex patterns for markdown to HTML conversion
RE_HEADER_H3 = re.compile(r'^### (.+)$', re.MULTILINE)
RE_HEADER_H2 = re.compile(r'^## (.+)$', re.MULTILINE)
RE_HEADER_H1 = re.compile(r'^# (.+)$', re.MULTILINE)
RE_BOLD = re.compile(r'\*\*(.+?)\*\*')
RE_ITALIC = re.compile(r'\*(.+?)\*')
RE_PAPER_NUM = re.compile(r'Paper (\d+)')
RE_DIGIT = re.compile(r'\d+')
RE_MULTI_PAPER = re.compile(r'\[(Paper \d+(?:,\s*Paper \d+)+)\]')
RE_MIXED_PAPER = re.compile(r'\[(Paper \d+(?:,\s*\d+)+)\]')
RE_PAPERS_PLURAL = re.compile(r'\[Papers (\d+(?:,\s*\d+)+)\]')
RE_SINGLE_PAPER = re.compile(r'\[Paper (\d+)\]')
RE_UNBRACKETED_PAPER = re.compile(r'(?<!data-paper-id=")(?<!">)(?<!\[)Paper (\d+)(?!\])')

from config import (
    DEFAULT_SYNTHESIS_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_APP_TITLE,
)


class OpenRouterSynthesisAgent:
    """Generate conference synthesis via OpenRouter using Gemini 2.5 Flash."""

    def __init__(self, api_key=None, model: str = None, debug: bool = False):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY.")

        default_headers = {k: v for k, v in {
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "X-Title": OPENROUTER_APP_TITLE,
        }.items() if v}

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers=default_headers,
        )
        self.model = model or DEFAULT_SYNTHESIS_MODEL
        self.debug = debug

    def generate(self, prompt: str) -> str:
        """Call the model and return the synthesis text."""
        if self.debug:
            print(f"🤖 Calling OpenRouter synthesis model: {self.model}")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )

        if not response.choices or not response.choices[0].message:
            raise RuntimeError("No response from OpenRouter synthesis model")

        return response.choices[0].message.content.strip()

def generate_synthesis(papers, categories, model=None, debug=False, conference_name=None):
    """Generate synthesis from papers and categories.

    Args:
        papers: List of enriched papers
        categories: List of categories
        model: Model to use for synthesis (default from config)
        debug: Enable verbose logging for the synthesis call
        conference_name: Optional human-readable conference name (e.g., "NeurIPS 2025")

    Returns:
        tuple: (synthesis_html, paper_index) where paper_index maps paper numbers to metadata
    """
    # Filter to papers that have been enriched
    enriched = [p for p in papers if p.get('key_findings') and p.get('novelty')]

    if len(enriched) == 0:
        return None, {}

    # Default model fallback when not provided
    model = model or DEFAULT_SYNTHESIS_MODEL

    print(f"Generating synthesis for {len(enriched)} enriched papers...")

    # Build paper index for later reference
    paper_index = {}
    for i, paper in enumerate(enriched, 1):
        paper_index[i] = {
            'title': paper['title'],
            'score': paper.get('score', paper.get('relevance_score', 'N/A')),
            'categories': paper.get('ai_categories', []),
            'pdf_url': paper.get('pdf_url', '')
        }

    # Prepare paper summaries for Claude
    paper_summaries = []
    for i, paper in enumerate(enriched, 1):
        score_val = paper.get('score', paper.get('relevance_score', 'N/A'))
        summary = f"""
Paper {i}: {paper['title']}
Score: {score_val} (relevance to your research)
Categories: {', '.join(paper.get('ai_categories', []))}
Novelty: {paper['novelty']}
Key Contribution: {paper['key_contribution']}
Key Findings: {paper['key_findings']}
"""
        paper_summaries.append(summary)

    # Create comprehensive prompt
    conf_label = conference_name or "this conference"
    prompt = f"""You are analyzing {len(enriched)} research papers presented at {conf_label} across these categories: {', '.join(categories)}.

Here are all the papers with their key insights:

{'='*80}
{chr(10).join(paper_summaries)}
{'='*80}

Please write a COMPREHENSIVE, critical synthesis of what someone should have learned at {conf_label}. Your synthesis should:

1. **Identify Major Trends**: What are the 3-5 dominant research directions? How are they connected? Reference MULTIPLE papers for each trend to show evidence.

2. **Highlight Surprising/Novel Findings**: What results were unexpected? What challenges existing assumptions? Cite specific examples.

3. **Make Connections**: Which papers complement each other? Which papers are in tension? What gaps exist? Draw connections across MANY papers.

4. **Assess Impact**: What work will likely be most influential? What represents genuine progress vs incremental work? Reference numerous examples.

5. **Critical Analysis**: Where is the field going? What problems remain unsolved? What approaches are overhyped? Be specific with citations.

6. **Practical Takeaways**: What should practitioners actually do with this research? Ground recommendations in specific papers.

**CRITICAL INSTRUCTIONS:**
- You MUST reference a LARGE number of papers throughout the synthesis (aim for 50-100+ paper citations)
- Use paper citations liberally: [Paper 5], [Paper 23], etc.
- Every claim should be supported by paper references
- Cover papers across ALL the major categories, not just a few
- When discussing a trend or finding, cite MULTIPLE supporting papers, not just one
- Make the synthesis LONGER and more detailed - aim for 2000-3000 words minimum
- Be comprehensive - you have {len(enriched)} papers to work with, use them!

Format your response as a well-structured synthesis with clear sections using markdown headers (##). Start with a strong title that mentions {conf_label}, followed by a concise executive summary (5-7 bullet points or short paragraphs) before the deep dive. Be critical and insightful - this should read like an expert's comprehensive analysis of the entire conference, not a surface-level summary of a few papers.

Focus on synthesizing insights across papers rather than listing individual papers, but REFERENCE MANY PAPERS to support your synthesis. Make bold claims when the evidence supports them."""

    # Call OpenRouter (Gemini 2.5 Flash) to generate synthesis
    try:
        agent = OpenRouterSynthesisAgent(model=model, debug=debug)
        synthesis = agent.generate(prompt)
        print(f"✓ Generated synthesis ({len(synthesis.split())} words)")

        # Convert paper references to HTML with tooltips
        synthesis_html = convert_synthesis_to_html(synthesis, paper_index)

        return synthesis_html, paper_index

    except Exception as e:
        print(f"Error generating synthesis: {e}")
        return None, {}

def convert_synthesis_to_html(text, paper_index):
    """Convert markdown synthesis with paper references to HTML with interactive tooltips."""
    if not text:
        return ""

    # Convert headers with styling
    text = RE_HEADER_H3.sub(r'<h3 style="color: #1c3664; font-weight: 600; margin-top: 25px;">\1</h3>', text)
    text = RE_HEADER_H2.sub(r'<h2 style="color: #1c3664; font-weight: 600; margin-top: 30px;">\1</h2>', text)
    text = RE_HEADER_H1.sub(r'<h1 style="color: #1c3664; font-weight: 600; margin-top: 20px;">\1</h1>', text)

    # Convert bold
    text = RE_BOLD.sub(r'<strong>\1</strong>', text)

    # Convert italic
    text = RE_ITALIC.sub(r'<em>\1</em>', text)

    # Convert paper references [Paper X] to interactive tooltips
    missing_papers = []

    def make_paper_link(paper_num):
        """Create a paper link for a given paper number."""
        if paper_num in paper_index:
            info = paper_index[paper_num]
            title = info['title'].replace('"', '&quot;').replace("'", '&#39;')
            score = info.get('score', 'N/A')
            categories = ', '.join(info.get('categories', []))
            pdf_url = info.get('pdf_url', '')

            # Store data attributes for JavaScript tooltip and PDF link
            pdf_attr = f' data-pdf-url="{pdf_url}"' if pdf_url else ''
            return f'<a class="paper-ref" href="{pdf_url}" target="_blank" data-paper-id="{paper_num}" data-title="{title}" data-score="{score}" data-categories="{categories}"{pdf_attr}>[Paper {paper_num}]</a>'
        else:
            missing_papers.append(paper_num)
            # Still make it look like a reference but with a warning style
            return f'<span class="paper-ref paper-ref-missing" data-paper-id="{paper_num}">[Paper {paper_num}]</span>'

    def replace_single_paper_ref(match):
        paper_num = int(match.group(1))
        return make_paper_link(paper_num)

    def replace_multi_paper_ref(match):
        """Handle [Paper X, Paper Y, Paper Z] patterns."""
        content = match.group(1)
        # Extract all paper numbers
        paper_nums = [int(n) for n in RE_PAPER_NUM.findall(content)]
        if not paper_nums:
            return match.group(0)
        # Create links for each paper
        links = [make_paper_link(num) for num in paper_nums]
        return '[' + ', '.join(links) + ']'

    def replace_mixed_ref(match):
        """Handle [Paper X, Y, Z] patterns where only first has 'Paper' prefix."""
        content = match.group(1)
        # Extract all numbers (first one after "Paper", rest are just numbers)
        paper_nums = [int(n) for n in RE_DIGIT.findall(content)]
        if not paper_nums:
            return match.group(0)
        # Create links for each paper
        links = [make_paper_link(num) for num in paper_nums]
        return '[' + ', '.join(links) + ']'

    # First, handle multi-paper brackets like [Paper 11, Paper 18, Paper 30]
    text = RE_MULTI_PAPER.sub(replace_multi_paper_ref, text)

    # Handle mixed format like [Paper 2, 19, 24, 92] where only first has "Paper"
    text = RE_MIXED_PAPER.sub(replace_mixed_ref, text)

    # Handle "Papers" plural format like [Papers 13, 111, 179, 308]
    text = RE_PAPERS_PLURAL.sub(replace_mixed_ref, text)

    # Then, handle single [Paper X] in brackets
    text = RE_SINGLE_PAPER.sub(replace_single_paper_ref, text)

    # Finally, handle unbracketed "Paper X" references
    # Use negative lookbehind/lookahead to skip already converted refs
    text = RE_UNBRACKETED_PAPER.sub(replace_single_paper_ref, text)

    if missing_papers:
        print(f"⚠️  Warning: {len(set(missing_papers))} paper references not found in index: {sorted(set(missing_papers))}")

    # Convert paragraphs (double newline)
    paragraphs = text.split('\n\n')
    html_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if para:
            # Don't wrap if it's already a heading
            if para.startswith('<h'):
                html_paragraphs.append(para)
            else:
                # Replace single newlines with <br>
                para = para.replace('\n', '<br>')
                html_paragraphs.append(f'<p>{para}</p>')

    return '\n\n'.join(html_paragraphs)

def synthesize_conference_summary(enriched_papers_file, output_file, conference_name=None):
    """Generate a critical synthesis of conference research."""

    # Load enriched papers
    try:
        with open(enriched_papers_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            papers = data.get('papers', [])
            categories = data.get('categories', [])
    except FileNotFoundError:
        print(f"Error: Could not find {enriched_papers_file}")
        print("Please run paper enrichment first: python enrich_papers.py")
        return
    except Exception as e:
        print(f"Error loading enriched papers: {e}")
        return

    # Generate synthesis
    synthesis_html, paper_index = generate_synthesis(papers, categories, conference_name=conference_name)

    if not synthesis_html:
        print("Failed to generate synthesis")
        return

    enriched = [p for p in papers if p.get('key_findings') and p.get('novelty')]

    # Build collapsible reference list HTML
    reference_html = '<details style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px;">\n'
    reference_html += '<summary style="cursor: pointer; font-weight: bold; font-size: 1.1em; color: #1c3664;">📚 Paper Reference Index ({} papers)</summary>\n'.format(len(paper_index))
    reference_html += '<div style="margin-top: 20px;">\n'

    for paper_num in sorted(paper_index.keys()):
        info = paper_index[paper_num]
        cats = ', '.join(info['categories'])
        pdf_link = f' <a href="{info["pdf_url"]}" target="_blank" style="color: #00c781; text-decoration: none;">📄 PDF</a>' if info.get('pdf_url') else ''
        reference_html += f'<p style="margin: 10px 0; padding: 10px; background: white; border-radius: 5px;">'
        reference_html += f'<strong>[Paper {paper_num}]</strong> {info["title"]}'
        reference_html += f'<br><small style="color: #666;">Score: {info["score"]} | {cats}</small>{pdf_link}</p>\n'

    reference_html += '</div>\n</details>'

    # Write HTML output file
    html_output = output_file.replace('.md', '.html')
    with open(html_output, 'w', encoding='utf-8') as f:
        f.write('<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; line-height: 1.8; color: #2c3e50;">\n')
        f.write(f'<div style="text-align: center; margin-bottom: 30px; padding: 30px; background: linear-gradient(135deg, #1c3664 0%, #0a1f44 100%); color: white; border-radius: 8px;">\n')
        f.write('<h1 style="margin: 0; color: white; font-weight: 600;">Research Synthesis</h1>\n')
        f.write(f'<p style="margin: 10px 0 0 0; color: #b8c5d6;">Analysis of {len(enriched)} papers across {len(categories)} research areas</p>\n')
        f.write('</div>\n')
        f.write(synthesis_html)
        f.write('\n\n')
        f.write(reference_html)
        f.write('\n</div>')

    print(f"✓ Synthesis written to {html_output}")
    print(f"References {len(enriched)} papers with correct tooltips")

if __name__ == "__main__":
    enriched_papers_file = "enriched_papers.json"
    output_file = "conference_synthesis.md"

    synthesize_conference_summary(enriched_papers_file, output_file)
