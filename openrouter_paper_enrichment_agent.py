#!/usr/bin/env python3
"""
OpenRouter agent for paper enrichment using Gemini 2.5 Flash.
Fetches PDFs and extracts key insights, descriptions, and categories.
"""

import json
import os
import re
import requests
from typing import Optional, Dict, Any, List
from io import BytesIO

from openai import OpenAI

# Gemini 2.5 Flash context limit (1M tokens ~ roughly 4M chars)
MAX_CONTEXT_CHARS = 1_000_000  # ~25% of context, leaving room for prompt and response


def fetch_pdf_text(pdf_url: str, timeout: int = 30) -> Optional[str]:
    """
    Fetch a PDF from URL and extract text content.

    Args:
        pdf_url: URL to the PDF file
        timeout: Request timeout in seconds

    Returns:
        Extracted text content or None if failed
    """
    try:
        # Try to import PyMuPDF (fitz) for PDF parsing
        import fitz  # PyMuPDF
    except ImportError:
        print("  ⚠ PyMuPDF not installed. Run: pip install PyMuPDF")
        return None

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(pdf_url, headers=headers, timeout=timeout)
        response.raise_for_status()

        # Parse PDF from bytes
        pdf_bytes = BytesIO(response.content)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())

        doc.close()
        return "\n".join(text_parts)

    except requests.RequestException as e:
        print(f"  ⚠ Failed to fetch PDF: {e}")
        return None
    except Exception as e:
        print(f"  ⚠ Failed to parse PDF: {e}")
        return None


class OpenRouterPaperEnrichmentAgent:
    """Agent that uses OpenRouter (Gemini 2.5 Flash) to enrich paper information."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, debug: bool = False):
        """Initialize the agent with OpenRouter API key and client configuration.

        Args:
            api_key: OpenRouter API key (falls back to OPENROUTER_API_KEY env var)
            model: Model to use (falls back to OPENROUTER_PAPER_MODEL env var, then 'google/gemini-2.5-flash')
            debug: Enable debug output
        """
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable.")

        base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

        referer = os.environ.get("OPENROUTER_HTTP_REFERER", "https://github.com/aldro61/PaperAtlas")
        app_title = os.environ.get("OPENROUTER_APP_TITLE", "PaperAtlas Paper Enrichment")
        default_headers = {k: v for k, v in {
            "HTTP-Referer": referer,
            "X-Title": app_title,
        }.items() if v}

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            default_headers=default_headers,
        )
        # Use Gemini 2.5 Flash for paper enrichment (1M token context)
        self.model = model or os.environ.get("OPENROUTER_PAPER_MODEL", "google/gemini-2.5-flash")
        self.debug = debug

    def enrich_paper(
        self,
        title: str,
        pdf_url: Optional[str],
        categories: List[str],
        score: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Enrich a paper with key insights and category assignment.

        Args:
            title: Paper title
            pdf_url: URL to the PDF (optional)
            categories: List of available categories to assign from
            score: Relevance score (optional, for context)

        Returns:
            Dict with key_findings, description, key_contribution, novelty, and categories
        """

        # Try to fetch and parse PDF content
        pdf_text = None
        trimmed = False

        if pdf_url:
            if self.debug:
                print(f"  📥 Fetching PDF from {pdf_url[:60]}...")
            pdf_text = fetch_pdf_text(pdf_url)

            if pdf_text:
                original_len = len(pdf_text)
                if original_len > MAX_CONTEXT_CHARS:
                    pdf_text = pdf_text[:MAX_CONTEXT_CHARS]
                    trimmed = True
                    print(f"  ⚠ PDF text trimmed from {original_len:,} to {MAX_CONTEXT_CHARS:,} chars")
                elif self.debug:
                    print(f"  ✓ PDF parsed: {original_len:,} chars")

        categories_str = ", ".join(categories)

        # Build prompt based on whether we have PDF content
        if pdf_text:
            prompt = f"""Analyze this research paper and extract key insights.

Paper Title: "{title}"
{f'Relevance Score: {score}' if score else ''}

Available Categories for Classification: {categories_str}

{'[NOTE: PDF content was trimmed due to length. Analysis based on available text.]' if trimmed else ''}

PAPER CONTENT:
{pdf_text}

Based on the paper content above, extract:
1. KEY FINDINGS: What is new? What is important? What does this paper bring to the field? (2-3 sentences)
2. DESCRIPTION: What the paper is about - summarize the main focus and approach (2-3 sentences)
3. KEY CONTRIBUTION: The main contribution or innovation (1-2 sentences)
4. NOVELTY: How is this work different from previous work? What existing limitations does it address? What new approach does it take? (2-3 sentences)
5. CATEGORIES: Assign 1-3 relevant categories from the available list above - be selective

Return ONLY a valid JSON object with this exact format:
{{"key_findings": "...", "description": "...", "key_contribution": "...", "novelty": "...", "categories": ["Category1", "Category2"]}}"""
        else:
            # No PDF content - use title-based analysis with web search
            prompt = f"""Analyze this research paper and extract key insights.

Paper Title: "{title}"
{f'Relevance Score: {score}' if score else ''}

Available Categories for Classification: {categories_str}

IMPORTANT: I couldn't fetch the PDF directly. You MUST use the web_search tool to search for this paper before providing any analysis. Do NOT attempt to answer based solely on the title - you must search for and read actual information about the paper first.

After searching, based on what you find (abstract, paper content, reviews, etc.), extract:
1. KEY FINDINGS: What is new? What is important? What does this paper bring to the field? (2-3 sentences)
2. DESCRIPTION: What the paper is about - summarize the main focus and approach (2-3 sentences)
3. KEY CONTRIBUTION: The main contribution or innovation (1-2 sentences)
4. NOVELTY: How is this work different from previous work? What existing limitations does it address? What new approach does it take? (2-3 sentences)
5. CATEGORIES: Assign 1-3 relevant categories from the available list above - be selective

Return ONLY a valid JSON object with this exact format:
{{"key_findings": "...", "description": "...", "key_contribution": "...", "novelty": "...", "categories": ["Category1", "Category2"]}}"""

        if self.debug:
            print(f"  🤖 Calling OpenRouter ({self.model})...")

        try:
            # If no PDF content, use :online suffix to force web search
            if not pdf_text:
                # Append :online to model name to enable automatic web search
                model_with_search = f"{self.model}:online"
                if self.debug:
                    print(f"  🔍 Using web search model: {model_with_search}")
            else:
                model_with_search = self.model

            response = self.client.chat.completions.create(
                model=model_with_search,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            final_response = None
            if response.choices and response.choices[0].message:
                final_response = response.choices[0].message.content

            if not final_response:
                if self.debug:
                    print("  ✗ No response from model")
                return None

            if self.debug:
                print(f"  ✓ Model returned response ({len(final_response)} chars)")

            # Parse JSON from response
            return self._parse_json_response(final_response)

        except Exception as e:
            print(f"  ✗ Error calling OpenRouter API: {e}")
            return None

    def _parse_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from model response, handling markdown code blocks."""
        try:
            # Remove markdown code blocks if present
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()

            # Find JSON object using brace matching
            start = response_text.find('{')
            if start == -1:
                if self.debug:
                    print(f"  ✗ No JSON object found in response")
                return None

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
                if self.debug:
                    print(f"  ✗ Malformed JSON - unmatched braces")
                return None

            json_str = response_text[start:end]
            enrichment = json.loads(json_str)

            if not isinstance(enrichment, dict):
                if self.debug:
                    print(f"  ✗ Response is not a JSON object")
                return None

            if self.debug:
                print(f"  ✓ Parsed enrichment: {list(enrichment.keys())}")

            return enrichment

        except json.JSONDecodeError as e:
            if self.debug:
                print(f"  ✗ JSON decode error: {e}")
            return None

    def generate_categories(self, papers: List[Dict[str, Any]]) -> List[str]:
        """
        Generate categories by analyzing all paper titles.

        Args:
            papers: List of paper dicts with 'title' key

        Returns:
            List of category names
        """
        titles_text = "\n".join([
            f"{i+1}. {paper['title']} (score: {paper.get('score', paper.get('relevance_score', 'N/A'))})"
            for i, paper in enumerate(papers)
        ])

        prompt = f"""Analyze these {len(papers)} paper titles and create high-level research categories that would effectively group them.

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

        if self.debug:
            print(f"  🤖 Generating categories for {len(papers)} papers...")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            if not response.choices or not response.choices[0].message:
                print("  ✗ No response from model")
                return self._default_categories()

            response_text = response.choices[0].message.content.strip()

            # Extract JSON array
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()

            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)

            categories = json.loads(response_text)

            if isinstance(categories, list) and all(isinstance(c, str) for c in categories):
                print(f"  ✓ Generated {len(categories)} categories")
                return categories
            else:
                print("  ✗ Invalid categories format")
                return self._default_categories()

        except Exception as e:
            print(f"  ✗ Error generating categories: {e}")
            return self._default_categories()

    def _default_categories(self) -> List[str]:
        """Return default categories as fallback."""
        return [
            "Machine Learning",
            "Deep Learning",
            "Natural Language Processing",
            "Computer Vision",
            "Reinforcement Learning",
            "Optimization",
            "Theory",
            "Applications",
            "Other"
        ]


if __name__ == "__main__":
    import sys

    debug_mode = '--debug' in sys.argv or '-d' in sys.argv

    # Test with a sample paper
    test_title = "Attention Is All You Need"
    test_pdf = "https://arxiv.org/pdf/1706.03762"
    test_categories = ["Deep Learning", "NLP", "Transformers", "Optimization"]

    if not debug_mode:
        print(f"Testing paper enrichment agent")
        print("=" * 80)
        print(f"Paper: {test_title}")
        print(f"PDF: {test_pdf}")
        print("=" * 80)
        print("Tip: Use --debug flag to see detailed execution steps")
        print("=" * 80)

    try:
        agent = OpenRouterPaperEnrichmentAgent(debug=debug_mode)
    except ValueError as e:
        print(f"✗ {e}")
        sys.exit(1)

    result = agent.enrich_paper(test_title, test_pdf, test_categories)

    if result:
        print("\n✓ Success!")
        print(json.dumps(result, indent=2))
    else:
        print("\n✗ Failed to enrich paper")

# TODO: Try to chunk and summarize very large PDFs in parts.
