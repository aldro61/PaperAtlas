#!/usr/bin/env python3
"""
OpenRouter agent with built-in web search for author enrichment.
Uses OpenRouter's OpenAI-compatible API with the `web_search` tool.
"""

import json
import os
from typing import Optional, Dict, Any

from openai import OpenAI, APITimeoutError

from config import (
    DEFAULT_AUTHOR_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_APP_TITLE,
)


class OpenRouterAuthorEnrichmentAgent:
    """Agent that uses OpenRouter (GPT-5-mini) with web search to enrich author information."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, debug: bool = False):
        """Initialize the agent with OpenRouter API key and client configuration.

        Args:
            api_key: OpenRouter API key (falls back to OPENROUTER_API_KEY env var)
            model: Model to use (default from config)
            debug: Enable debug output
        """
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable.")

        default_headers = {k: v for k, v in {
            "HTTP-Referer": OPENROUTER_HTTP_REFERER,
            "X-Title": OPENROUTER_APP_TITLE,
        }.items() if v}

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers=default_headers,
            timeout=30.0,  # 30 second timeout for author enrichment
        )
        self.model = model or DEFAULT_AUTHOR_MODEL
        self.debug = debug

    def get_author_info(self, author_name: str, paper_titles: list[str]) -> Optional[Dict[str, Any]]:
        """
        Get author affiliation and role using OpenRouter with built-in web search.

        Args:
            author_name: Name of the researcher
            paper_titles: List of their paper titles (up to 3 for context)

        Returns:
            Dict with affiliation, role, photo_url, and profile_url, or None if failed
        """

        paper_list = "\n".join(f"- {title[:100]}" for title in paper_titles[:3])

        prompt = f"""Find information about this academic researcher:

Author: {author_name}

Their papers include:
{paper_list}

Please search the web to find:
1. Their PRIMARY current affiliation (university or company name ONLY - no departments, labs, or addresses)
2. Their SINGLE most senior role (e.g., PhD Student, Postdoc, Assistant Professor, Associate Professor, Professor, Research Scientist)
3. A professional photo URL (from their university/company webpage, Google Scholar, or research profile)
4. A link to their profile (prioritize: personal webpage > Google Scholar > university profile page)

IMPORTANT FORMATTING RULES:
- affiliation: Use ONLY the institution name. Examples:
  - "Tsinghua University" (NOT "Tsinghua University, Department of Computer Science")
  - "Google DeepMind" (NOT "Google DeepMind, London, UK")
  - "MIT" (NOT "Massachusetts Institute of Technology, CSAIL")
- role: Use ONE concise title. Examples:
  - "Professor" (NOT "Full Professor of Computer Science")
  - "Research Scientist" (NOT "Senior Research Scientist, AI Division")
  - "PhD Student" (NOT "PhD Candidate in Machine Learning")

When you have found the information, return ONLY a JSON object with this exact format:
{{"affiliation": "Institution Name", "role": "Role Title", "photo_url": "https://...", "profile_url": "https://..."}}

If you cannot find a photo or profile link, set those fields to null. Only use "Unknown" if you genuinely could not find the information after searching."""

        if self.debug:
            print(f"\n{'='*80}")
            print(f"🔬 DEBUG MODE: Enriching author '{author_name}' via OpenRouter")
            print(f"{'='*80}")

        try:
            if self.debug:
                print(f"\n🤖 Calling OpenRouter (model: {self.model}) with web search...")

            response = self.client.responses.create(
                model=self.model,
                tools=[{"type": "web_search"}],
                input=prompt,
            )

            final_response = None
            for item in response.output or []:
                if item.type == "message":
                    for content in item.content:
                        if content.type == "output_text":
                            final_response = content.text
                            break

            if not final_response:
                if self.debug:
                    print("   ✗ No response from model")
                return None

            if self.debug:
                print(f"\n   ✅ Model returned response")
                print(f"   📄 Response: {final_response[:300]}...")

            try:
                if '```json' in final_response:
                    final_response = final_response.split('```json')[1].split('```')[0].strip()
                elif '```' in final_response:
                    final_response = final_response.split('```')[1].split('```')[0].strip()

                import re
                json_match = re.search(r'\{[^}]+\}', final_response, re.DOTALL)
                if json_match:
                    final_response = json_match.group(0)

                author_info = json.loads(final_response)

                if self.debug:
                    print(f"\n   ✅ Successfully parsed JSON:")
                    print(f"      Affiliation: {author_info.get('affiliation')}")
                    print(f"      Role: {author_info.get('role')}")
                    print(f"      Photo URL: {author_info.get('photo_url')}")
                    print(f"      Profile URL: {author_info.get('profile_url')}")
                    print(f"{'='*80}\n")

                return author_info

            except json.JSONDecodeError as e:
                if self.debug:
                    print(f"\n   ✗ JSON decode error: {e}")
                    print(f"      Response: {final_response[:400]}")
                else:
                    print(f"  ✗ JSON decode error: {e}")
                    print(f"     Response: {final_response[:200]}")
                return None

        except APITimeoutError:
            print(f"  ✗ Timeout (30s) enriching author: {author_name}")
            return None
        except Exception as e:
            print(f"  ✗ Error calling OpenRouter API: {e}")
            return None


def get_author_info_with_openrouter(author_name: str, paper_titles: list[str]) -> Optional[Dict[str, Any]]:
    """
    Wrapper function to match the signature of other enrichment helpers.
    """
    agent = OpenRouterAuthorEnrichmentAgent()
    return agent.get_author_info(author_name, paper_titles)


if __name__ == "__main__":
    import sys

    debug_mode = '--debug' in sys.argv or '-d' in sys.argv

    test_author = "Yoshua Bengio"
    test_papers = [
        "Attention Is All You Need",
        "Deep Learning",
        "Neural Machine Translation"
    ]

    if not debug_mode:
        print(f"Testing agent with author: {test_author}")
        print("=" * 80)
        print("Tip: Use --debug flag to see detailed execution steps")
        print("=" * 80)

    try:
        agent = OpenRouterAuthorEnrichmentAgent(debug=debug_mode)
    except ValueError as e:
        print(f"✗ {e}")
        sys.exit(1)

    result = agent.get_author_info(test_author, test_papers)

    if not debug_mode:
        if result:
            print("\n✓ Success!")
            print(json.dumps(result, indent=2))
        else:
            print("\n✗ Failed to get author information")
