#!/usr/bin/env python3
"""
PaperAtlas Web UI - A nice interface for scraping Scholar Inbox conferences.

This provides a web-based UI where users can:
1. Enter their Scholar Inbox secret login link
2. Select a conference from a dropdown
3. Watch the extraction progress in real-time
4. Download the resulting CSV

Usage:
    python app.py
    Then open http://localhost:5000 in your browser
"""

import asyncio
import csv
import json
import os
import queue
import re
import sys
import threading
from collections import defaultdict
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_file
from playwright.async_api import async_playwright

# Import enrichment functions
sys.path.insert(0, os.path.dirname(__file__))
from enrich_authors import parse_authors, analyze_authors
from openrouter_author_enrichment_agent import OpenRouterAuthorEnrichmentAgent
from openrouter_paper_enrichment_agent import OpenRouterPaperEnrichmentAgent
from generate_website import generate_website
from synthesize_conference import generate_synthesis
from config import (
    HIGHLY_RELEVANT_THRESHOLD,
    AUTHOR_ENRICHMENT_WORKERS,
    PAPER_ENRICHMENT_WORKERS,
    SCHOLAR_INBOX_API_BASE,
    DEFAULT_AUTHOR_MODEL,
    DEFAULT_PAPER_MODEL,
    DEFAULT_SYNTHESIS_MODEL,
    OPENROUTER_API_KEY,
)

API_BASE = SCHOLAR_INBOX_API_BASE

app = Flask(__name__)

# Global state for tracking progress
progress_queues = {}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PaperAtlas - Scholar Inbox Scraper</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
            padding: 40px 20px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
        }

        .banner {
            width: 100%;
            max-width: 900px;
            border-radius: 14px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
            display: block;
            margin: 0 auto 24px;
        }

        .subtitle {
            text-align: center;
            color: #888;
            margin-bottom: 40px;
        }

        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .form-group {
            margin-bottom: 25px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #b0b0b0;
        }

        .label-hint {
            font-size: 0.85rem;
            color: #666;
            margin-top: 4px;
        }

        input[type="text"], input[type="url"], select {
            width: 100%;
            padding: 14px 16px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            background: rgba(0, 0, 0, 0.3);
            color: #fff;
            font-size: 1rem;
            transition: border-color 0.3s, box-shadow 0.3s;
        }

        input:focus, select:focus {
            outline: none;
            border-color: #00d4ff;
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
        }

        select {
            cursor: pointer;
        }

        select option {
            background: #1a1a2e;
            color: #fff;
        }

        button {
            width: 100%;
            padding: 16px;
            border: none;
            border-radius: 10px;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            color: #fff;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        button:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0, 212, 255, 0.3);
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        /* Workflow Steps */
        .workflow {
            display: none;
        }

        .workflow.active {
            display: block;
        }

        .steps {
            display: flex;
            flex-direction: column;
            gap: 15px;
            margin-bottom: 25px;
        }

        .step {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 15px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 10px;
            transition: all 0.3s;
        }

        .step.active {
            background: rgba(0, 212, 255, 0.1);
            border-left: 3px solid #00d4ff;
        }

        .step.completed {
            background: rgba(0, 255, 136, 0.1);
            border-left: 3px solid #00ff88;
        }

        .step.error {
            background: rgba(255, 68, 68, 0.1);
            border-left: 3px solid #ff4444;
        }

        .step-icon {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(255, 255, 255, 0.1);
            font-size: 1.2rem;
        }

        .step.active .step-icon {
            background: #00d4ff;
            animation: pulse 1.5s infinite;
        }

        .step.completed .step-icon {
            background: #00ff88;
        }

        .step.error .step-icon {
            background: #ff4444;
        }

        @keyframes pulse {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.1); opacity: 0.8; }
        }

        .step-content {
            flex: 1;
        }

        .step-title {
            font-weight: 600;
            margin-bottom: 3px;
        }

        .step-detail {
            font-size: 0.85rem;
            color: #888;
        }

        /* Console Output */
        .console {
            background: #0a0a0a;
            border-radius: 10px;
            padding: 15px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.85rem;
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .console-line {
            margin: 4px 0;
            line-height: 1.4;
        }

        .console-line.info { color: #00d4ff; }
        .console-line.success { color: #00ff88; }
        .console-line.error { color: #ff4444; }
        .console-line.warning { color: #ffaa00; }

        /* Results */
        .results {
            display: none;
            text-align: center;
        }

        .results.active {
            display: block;
        }

        .results h2 {
            color: #00ff88;
            margin-bottom: 20px;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 25px;
        }

        .stat {
            background: rgba(0, 0, 0, 0.3);
            padding: 20px;
            border-radius: 10px;
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .stat-label {
            color: #888;
            font-size: 0.9rem;
            margin-top: 5px;
        }

        .download-btn {
            display: inline-block;
            padding: 14px 40px;
            background: linear-gradient(90deg, #00ff88, #00d4ff);
            color: #000;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 600;
            transition: transform 0.2s;
        }

        .download-btn:hover {
            transform: translateY(-2px);
        }

        .restart-btn {
            margin-top: 15px;
            background: transparent;
            border: 2px solid rgba(255, 255, 255, 0.2);
            color: #888;
        }

        .restart-btn:hover {
            border-color: #00d4ff;
            color: #00d4ff;
        }

        /* Loading spinner */
        .spinner {
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top-color: #fff;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            display: inline-block;
            margin-right: 10px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .hidden {
            display: none;
        }

        .error-message {
            margin-top: 20px;
            padding: 15px;
            background: rgba(220, 38, 38, 0.1);
            border: 1px solid rgba(220, 38, 38, 0.3);
            border-radius: 8px;
            color: #fca5a5;
            font-size: 14px;
        }

        .error-message strong {
            color: #f87171;
        }

        .error-message code {
            background: rgba(0, 0, 0, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.9em;
        }

        .warning-message {
            margin-top: 20px;
            padding: 15px;
            background: rgba(251, 191, 36, 0.15);
            border: 1px solid rgba(251, 191, 36, 0.4);
            border-radius: 8px;
            color: #fcd34d;
            font-size: 14px;
        }

        .warning-message strong {
            color: #fbbf24;
        }

        .warning-message code {
            background: rgba(0, 0, 0, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.9em;
        }

        .model-section.disabled {
            opacity: 0.5;
            pointer-events: none;
        }

        /* Model Selection Styles */
        .model-section {
            margin-top: 25px;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }

        .section-label {
            font-size: 1.1rem;
            font-weight: 600;
            color: #e0e0e0;
            margin-bottom: 5px;
        }

        .model-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }

        .model-item {
            background: rgba(0, 0, 0, 0.2);
            padding: 15px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            min-width: 240px;
        }

        .model-item label {
            font-size: 0.9rem;
            font-weight: 500;
            margin-bottom: 8px;
        }

        .model-input {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
            color: #e0e0e0;
            font-size: 0.85rem;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        .model-input:focus {
            outline: none;
            border-color: rgba(96, 165, 250, 0.5);
            box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.1);
        }

        .model-input::placeholder {
            color: #666;
        }

        .model-hint {
            font-size: 0.75rem;
            color: #666;
            margin-top: 6px;
        }

        /* Editable dropdown combo */
        .model-combo {
            position: relative;
        }

        .model-combo .model-input {
            padding-right: 38px; /* make space for the arrow button */
        }

        .combo-toggle {
            position: absolute;
            right: 6px;
            top: 50%;
            transform: translateY(-50%) !important;
            border: none;
            background: rgba(255, 255, 255, 0.08);
            color: #d1d5db;
            width: 28px;
            height: 28px;
            line-height: 28px;
            padding: 0;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.15s ease, color 0.15s ease;
            outline: none;
            box-sizing: border-box;
        }

        .combo-toggle:hover {
            background: rgba(255, 255, 255, 0.15);
            color: #fff;
            transform: translateY(-50%) !important; /* keep position fixed on hover */
            box-shadow: none !important;
        }

        .combo-toggle:active,
        .combo-toggle:focus {
            transform: translateY(-50%) !important;
        }

        .combo-list {
            position: absolute;
            top: calc(100% + 6px);
            left: 0;
            right: 0;
            background: #0f172a;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
            z-index: 20;
            max-height: 220px;
            overflow-y: auto;
            display: none;
        }

        .combo-list.open {
            display: block;
        }

        .combo-option {
            width: 100%;
            text-align: left;
            padding: 10px 12px;
            background: transparent;
            border: none;
            color: #e5e7eb;
            cursor: pointer;
            font-size: 0.9rem;
        }

        .combo-option:hover {
            background: rgba(255, 255, 255, 0.08);
        }
    </style>
</head>
<body>
    <div class="container">
        <img src="/banner.png" alt="PaperAtlas Banner" class="banner">
        <p class="subtitle">Extract papers from <a href="https://scholar-inbox.com" target="_blank" style="color: #60a5fa;">Scholar Inbox</a> conferences</p>

        <!-- Setup Form -->
        <div class="card" id="setupCard">
            <div class="form-group">
                <label for="loginLink">Scholar Inbox Login Link</label>
                <input type="url" id="loginLink" placeholder="https://scholar-inbox.com/login?token=..." required>
                <p class="label-hint">Find this in Scholar Inbox Settings → "Secret login link"</p>
            </div>

            <div class="form-group">
                <label for="conference">Conference</label>
                <select id="conference" disabled>
                    <option value="">Enter login link first...</option>
                </select>
            </div>

            <div class="form-group hidden" id="reuseSection">
                <label>
                    <input type="checkbox" id="reuseCheckbox" style="width:auto; margin-right:8px;">
                    Reuse existing results
                </label>
                <p class="label-hint" id="reuseHint">Found existing output files. Enable to skip fresh extraction.</p>
            </div>

            <!-- Model Selection Section -->
            <div class="form-group model-section">
                <label class="section-label">Model Configuration</label>
                <p class="label-hint" style="margin-bottom: 15px;">Select from recommended models or type any <a href="https://openrouter.ai/models" target="_blank" style="color: #60a5fa;">OpenRouter model ID</a>.</p>

                <div class="model-grid">
                    <div class="model-item">
                        <label for="authorModel">👥 Author Enrichment</label>
                        <div class="model-combo">
                            <input type="text" id="authorModel" class="model-input"
                                   value="''' + DEFAULT_AUTHOR_MODEL + '''" placeholder="Type a model id...">
                            <button type="button" class="combo-toggle" aria-label="Select author model" data-list="authorModelOptions">▾</button>
                            <div class="combo-list" id="authorModelOptions">
                                <button type="button" class="combo-option" data-value="openai/gpt-5-mini">GPT-5 Mini (default)</button>
                                <button type="button" class="combo-option" data-value="openai/gpt-5">GPT-5</button>
                                <button type="button" class="combo-option" data-value="google/gemini-2.5-flash">Gemini 2.5 Flash</button>
                                <button type="button" class="combo-option" data-value="google/gemini-3-pro-preview">Gemini 3 Pro Preview</button>
                                <button type="button" class="combo-option" data-value="anthropic/claude-sonnet-4.5">Claude Sonnet 4.5</button>
                                <button type="button" class="combo-option" data-value="anthropic/claude-opus-4.5">Claude Opus 4.5</button>
                            </div>
                        </div>
                        <p class="model-hint">Web search for author affiliations</p>
                    </div>

                    <div class="model-item">
                        <label for="paperModel">🔬 Paper Enrichment</label>
                        <div class="model-combo">
                            <input type="text" id="paperModel" class="model-input"
                                   value="''' + DEFAULT_PAPER_MODEL + '''" placeholder="Type a model id...">
                            <button type="button" class="combo-toggle" aria-label="Select paper model" data-list="paperModelOptions">▾</button>
                            <div class="combo-list" id="paperModelOptions">
                                <button type="button" class="combo-option" data-value="openai/gpt-5-mini">GPT-5 Mini (default)</button>
                                <button type="button" class="combo-option" data-value="openai/gpt-5">GPT-5</button>
                                <button type="button" class="combo-option" data-value="google/gemini-2.5-flash">Gemini 2.5 Flash</button>
                                <button type="button" class="combo-option" data-value="google/gemini-3-pro-preview">Gemini 3 Pro Preview</button>
                                <button type="button" class="combo-option" data-value="anthropic/claude-sonnet-4.5">Claude Sonnet 4.5</button>
                                <button type="button" class="combo-option" data-value="anthropic/claude-opus-4.5">Claude Opus 4.5</button>
                            </div>
                        </div>
                        <p class="model-hint">PDF analysis & key insights</p>
                    </div>

                    <div class="model-item">
                        <label for="synthesisModel">🧠 Synthesis</label>
                        <div class="model-combo">
                            <input type="text" id="synthesisModel" class="model-input"
                                   value="''' + DEFAULT_SYNTHESIS_MODEL + '''" placeholder="Type a model id...">
                            <button type="button" class="combo-toggle" aria-label="Select synthesis model" data-list="synthesisModelOptions">▾</button>
                            <div class="combo-list" id="synthesisModelOptions">
                                <button type="button" class="combo-option" data-value="openai/gpt-5-mini">GPT-5 Mini</button>
                                <button type="button" class="combo-option" data-value="openai/gpt-5">GPT-5 (default)</button>
                                <button type="button" class="combo-option" data-value="google/gemini-2.5-flash">Gemini 2.5 Flash</button>
                                <button type="button" class="combo-option" data-value="google/gemini-3-pro-preview">Gemini 3 Pro Preview</button>
                                <button type="button" class="combo-option" data-value="anthropic/claude-sonnet-4.5">Claude Sonnet 4.5</button>
                                <button type="button" class="combo-option" data-value="anthropic/claude-opus-4.5">Claude Opus 4.5</button>
                            </div>
                        </div>
                        <p class="model-hint">Conference trend analysis</p>
                    </div>
                </div>
            </div>

            <button id="startBtn" disabled>
                <span class="spinner hidden"></span>
                <span class="btn-text">Start Extraction</span>
            </button>

            <div id="apiKeyWarning" class="warning-message hidden">
                <strong>⚠️ OpenRouter API Key Required</strong><br>
                To use PaperAtlas, you need to set the <code>OPENROUTER_API_KEY</code> environment variable.<br><br>
                <strong>How to fix:</strong><br>
                1. Get an API key from <a href="https://openrouter.ai/keys" target="_blank" style="color: #60a5fa;">openrouter.ai/keys</a><br>
                2. Set it in your terminal: <code>export OPENROUTER_API_KEY="your-key-here"</code><br>
                3. Restart PaperAtlas
            </div>

            <div id="validationError" class="error-message hidden"></div>
        </div>

        <!-- Workflow Progress -->
        <div class="card workflow" id="workflowCard">
            <div class="steps">
                <div class="step" data-step="login">
                    <div class="step-icon">🔐</div>
                    <div class="step-content">
                        <div class="step-title">Authenticating</div>
                        <div class="step-detail">Logging in to Scholar Inbox...</div>
                    </div>
                </div>
                <div class="step" data-step="sessions">
                    <div class="step-icon">📅</div>
                    <div class="step-content">
                        <div class="step-title">Fetching Sessions</div>
                        <div class="step-detail">Getting conference schedule...</div>
                    </div>
                </div>
                <div class="step" data-step="papers">
                    <div class="step-icon">📄</div>
                    <div class="step-content">
                        <div class="step-title">Extracting Papers</div>
                        <div class="step-detail">Downloading paper data...</div>
                    </div>
                </div>
                <div class="step" data-step="save">
                    <div class="step-icon">💾</div>
                    <div class="step-content">
                        <div class="step-title">Saving Results</div>
                        <div class="step-detail">Writing CSV file...</div>
                    </div>
                </div>
                <div class="step" data-step="authors">
                    <div class="step-icon">👥</div>
                    <div class="step-content">
                        <div class="step-title">Enriching Authors</div>
                        <div class="step-detail">Finding affiliations and roles...</div>
                    </div>
                </div>
                <div class="step" data-step="papers_enrichment">
                    <div class="step-icon">🔬</div>
                    <div class="step-content">
                        <div class="step-title">Enriching Papers</div>
                        <div class="step-detail">Extracting key insights...</div>
                    </div>
                </div>
                <div class="step" data-step="synthesis">
                    <div class="step-icon">🧠</div>
                    <div class="step-content">
                        <div class="step-title">Generating Synthesis</div>
                        <div class="step-detail">Summarizing conference insights...</div>
                    </div>
                </div>
                <div class="step" data-step="website">
                    <div class="step-icon">🌐</div>
                    <div class="step-content">
                        <div class="step-title">Generating Website</div>
                        <div class="step-detail">Building interactive HTML...</div>
                    </div>
                </div>
            </div>

            <div class="console" id="console"></div>
        </div>

        <!-- Results -->
        <div class="card results" id="resultsCard">
            <h2>Extraction Complete!</h2>
            <div class="stats">
                <div class="stat">
                    <div class="stat-value" id="statPapers">0</div>
                    <div class="stat-label">Papers</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="statSessions">0</div>
                    <div class="stat-label">Sessions</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="statHighRelevance">0</div>
                    <div class="stat-label">High Relevance</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="statAuthors">0</div>
                    <div class="stat-label">Authors Enriched</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="statEnrichedPapers">0</div>
                    <div class="stat-label">Papers Enriched</div>
                </div>
            </div>
            <a href="#" class="download-btn" id="openWebsiteBtn" target="_blank">🌐 Open Website</a>
            <br><br>
            <a href="#" class="download-btn" id="downloadBtn" style="background: linear-gradient(90deg, #667eea, #764ba2);">📥 Download CSV</a>
            <br>
            <button class="restart-btn" onclick="restart()">Start New Extraction</button>
        </div>
    </div>

    <script>
        const loginInput = document.getElementById('loginLink');
        const conferenceSelect = document.getElementById('conference');
        const startBtn = document.getElementById('startBtn');
        const setupCard = document.getElementById('setupCard');
        const workflowCard = document.getElementById('workflowCard');
        const resultsCard = document.getElementById('resultsCard');
        const consoleDiv = document.getElementById('console');
        const validationError = document.getElementById('validationError');
        const apiKeyWarning = document.getElementById('apiKeyWarning');
        const modelSection = document.querySelector('.model-section');
        const reuseSection = document.getElementById('reuseSection');
        const reuseCheckbox = document.getElementById('reuseCheckbox');
        const reuseHint = document.getElementById('reuseHint');
        const authorModelSelect = document.getElementById('authorModel');
        const paperModelSelect = document.getElementById('paperModel');
        const synthesisModelSelect = document.getElementById('synthesisModel');

        let sessionId = null;
        let hasApiKey = false;
        let eventSource = null;
        let conferenceFetchTimeout = null;

        function setupModelCombo(inputId, listId) {
            const input = document.getElementById(inputId);
            const list = document.getElementById(listId);
            if (!input || !list) return;

            const toggle = list.previousElementSibling;
            if (!toggle || !toggle.classList.contains('combo-toggle')) return;

            const closeList = () => {
                list.classList.remove('open');
                toggle.setAttribute('aria-expanded', 'false');
            };

            const openList = () => {
                list.classList.add('open');
                toggle.setAttribute('aria-expanded', 'true');
            };

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                const isOpen = list.classList.contains('open');
                if (isOpen) {
                    closeList();
                } else {
                    openList();
                }
            });

            list.querySelectorAll('.combo-option').forEach(option => {
                option.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const value = option.dataset.value || option.textContent.trim();
                    input.value = value;
                    closeList();
                    input.focus();
                });
            });

            document.addEventListener('click', (e) => {
                if (!list.contains(e.target) && e.target !== toggle && e.target !== input) {
                    closeList();
                }
            });

            // If cleared, restore default to first option on blur
            input.addEventListener('blur', () => ensureDefaultModel(inputId, listId));
        }

        setupModelCombo('authorModel', 'authorModelOptions');
        setupModelCombo('paperModel', 'paperModelOptions');
        setupModelCombo('synthesisModel', 'synthesisModelOptions');

        function ensureDefaultModel(inputId, listId) {
            const input = document.getElementById(inputId);
            const list = document.getElementById(listId);
            if (!input || !list) return;
            const first = list.querySelector('.combo-option');
            if (!first) return;
            if (!input.value || input.value.trim() === '') {
                input.value = first.dataset.value || first.textContent.trim();
            }
        }

        // Seed defaults on load
        ensureDefaultModel('authorModel', 'authorModelOptions');
        ensureDefaultModel('paperModel', 'paperModelOptions');
        ensureDefaultModel('synthesisModel', 'synthesisModelOptions');

        // Check dependencies on page load
        async function checkDependencies(conferenceName = '') {
            try {
                const query = conferenceName ? `?conference_name=${encodeURIComponent(conferenceName)}` : '';
                const response = await fetch(`/api/check-dependencies${query}`);
                const data = await response.json();

                // Track API key status
                hasApiKey = data.openrouter_api;

                // Handle missing API key with dedicated warning
                if (!data.openrouter_api) {
                    apiKeyWarning.classList.remove('hidden');
                    modelSection.classList.add('disabled');
                    startBtn.disabled = true;
                } else {
                    apiKeyWarning.classList.add('hidden');
                    modelSection.classList.remove('disabled');
                }

                // Handle other missing dependencies (like Playwright)
                if (!data.playwright) {
                    validationError.innerHTML = `
                        <strong>Missing Dependency:</strong> Playwright<br>
                        • Install Playwright: <code>pip install playwright && python -m playwright install chromium</code>
                    `;
                    validationError.classList.remove('hidden');
                    startBtn.disabled = true;
                    return false;
                } else if (data.openrouter_api) {
                    // Only hide validation error if API key is also present
                    validationError.classList.add('hidden');
                }

                if (!data.success) {
                    startBtn.disabled = true;
                    return false;
                }

                const hasPartials = data.papers_exists || data.authors_exists;
                if (hasPartials) {
                    reuseSection.classList.remove('hidden');
                    const parts = [];
                    if (data.papers_exists) parts.push('papers');
                    if (data.authors_exists) parts.push('authors');
                    const dt = data.reuse_timestamp ? new Date(data.reuse_timestamp) : null;
                    const dateStr = dt ? dt.toLocaleString() : 'unknown time';
                    reuseHint.textContent = `Found existing ${parts.join(' and ')} data (oldest collected: ${dateStr}). Enable to reuse instead of refetching.`;
                } else {
                    reuseSection.classList.add('hidden');
                    reuseCheckbox.checked = false;
                }

                return true;
            } catch (err) {
                console.error('Dependency check failed:', err);
                return true; // Don't block if check fails
            }
        }

        checkDependencies();

        function normalizeLoginLink(link) {
            return link.startsWith('http') ? link : `https://${link}`;
        }

        function isScholarInboxLink(link) {
            try {
                const url = new URL(normalizeLoginLink(link));
                const host = url.hostname.toLowerCase();
                return host.includes('scholar-inbox.com') || host.includes('scholarinbox.com');
            } catch (err) {
                return false;
            }
        }

        async function fetchConferences(link) {
            const normalizedLink = normalizeLoginLink(link);
            conferenceSelect.disabled = true;
            startBtn.disabled = true;
            conferenceSelect.innerHTML = '<option value="">Loading conferences...</option>';

            try {
                const response = await fetch('/api/conferences', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ login_link: normalizedLink })
                });
                const data = await response.json();

                if (data.success) {
                    conferenceSelect.innerHTML = '<option value="">Select a conference...</option>';
                    data.conferences.forEach(conf => {
                        const option = document.createElement('option');
                        option.value = conf.conference_url;
                        option.textContent = `${conf.short_title} - ${conf.full_title}`;
                        conferenceSelect.appendChild(option);
                    });
                    conferenceSelect.disabled = false;
                } else {
                    conferenceSelect.innerHTML = '<option value="">Error: ' + data.error + '</option>';
                }
            } catch (err) {
                conferenceSelect.innerHTML = '<option value="">Error fetching conferences</option>';
            }
        }

        // Validate login link and fetch conferences
        loginInput.addEventListener('input', () => {
            const link = loginInput.value.trim();
            clearTimeout(conferenceFetchTimeout);

            if (!link) {
                conferenceSelect.innerHTML = '<option value="">Enter login link first...</option>';
                startBtn.disabled = true;
                return;
            }

            if (!isScholarInboxLink(link)) {
                conferenceSelect.innerHTML = '<option value="">Enter a Scholar Inbox login link...</option>';
                startBtn.disabled = true;
                return;
            }

            conferenceFetchTimeout = setTimeout(() => fetchConferences(link), 300);
        });

        // Enable start button when conference is selected (only if API key is present)
        conferenceSelect.addEventListener('change', () => {
            // Only enable if conference selected AND API key is present
            startBtn.disabled = !conferenceSelect.value || !hasApiKey;
            const selectedOption = conferenceSelect.options[conferenceSelect.selectedIndex];
            const conferenceName = selectedOption ? selectedOption.textContent : '';
            if (conferenceSelect.value) {
                checkDependencies(conferenceName);
            } else {
                reuseSection.classList.add('hidden');
                reuseCheckbox.checked = false;
            }
        });

        // Start extraction
        startBtn.addEventListener('click', async () => {
            const loginLink = normalizeLoginLink(loginInput.value.trim());
            const conference = conferenceSelect.value;
            const selectedOption = conferenceSelect.options[conferenceSelect.selectedIndex];
            const conferenceName = selectedOption ? selectedOption.textContent : '';

            // Ensure model defaults if inputs are empty
            ensureDefaultModel('authorModel', 'authorModelOptions');
            ensureDefaultModel('paperModel', 'paperModelOptions');
            ensureDefaultModel('synthesisModel', 'synthesisModelOptions');

            if (!loginLink || !conference) return;

            // Double-check API key before proceeding
            if (!hasApiKey) {
                apiKeyWarning.classList.remove('hidden');
                return;
            }

            // Show workflow
            setupCard.style.display = 'none';
            workflowCard.classList.add('active');
            consoleDiv.innerHTML = '';

            // Reset steps
            document.querySelectorAll('.step').forEach(s => {
                s.classList.remove('active', 'completed', 'error');
            });

            // Start the extraction
            try {
                const response = await fetch('/api/extract', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        login_link: loginLink,
                        conference,
                        conference_name: conferenceName,
                        reuse_existing: reuseCheckbox.checked,
                        author_model: authorModelSelect.value,
                        paper_model: paperModelSelect.value,
                        synthesis_model: synthesisModelSelect.value
                    })
                });
                const data = await response.json();

                if (data.session_id) {
                    sessionId = data.session_id;
                    pollProgress();
                }
            } catch (err) {
                addConsoleLine('Error starting extraction: ' + err.message, 'error');
            }
        });

        function pollProgress() {
            const poll = async () => {
                try {
                    const response = await fetch(`/api/progress/${sessionId}`);
                    const data = await response.json();

                    // Update steps
                    if (data.current_step) {
                        document.querySelectorAll('.step').forEach(s => {
                            const stepName = s.dataset.step;
                            if (data.completed_steps.includes(stepName)) {
                                s.classList.remove('active');
                                s.classList.add('completed');
                            } else if (stepName === data.current_step) {
                                s.classList.add('active');
                            }
                        });
                    }

                    // Update step details
                    if (data.step_detail) {
                        const activeStep = document.querySelector('.step.active .step-detail');
                        if (activeStep) {
                            activeStep.textContent = data.step_detail;
                        }
                    }

                    // Add console lines
                    if (data.new_logs) {
                        data.new_logs.forEach(log => {
                            addConsoleLine(log.message, log.type);
                        });
                    }

                    // Check if done
                    if (data.status === 'completed') {
                        showResults(data.stats);
                        return;
                    } else if (data.status === 'error') {
                        const errorStep = document.querySelector('.step.active');
                        if (errorStep) {
                            errorStep.classList.remove('active');
                            errorStep.classList.add('error');
                        }
                        addConsoleLine('Extraction failed: ' + data.error, 'error');
                        return;
                    }

                    // Continue polling
                    setTimeout(poll, 500);
                } catch (err) {
                    setTimeout(poll, 1000);
                }
            };
            poll();
        }

        function addConsoleLine(message, type = 'info') {
            const line = document.createElement('div');
            line.className = `console-line ${type}`;
            line.textContent = `> ${message}`;
            consoleDiv.appendChild(line);
            consoleDiv.scrollTop = consoleDiv.scrollHeight;
        }

        function showResults(stats) {
            document.querySelectorAll('.step').forEach(s => {
                s.classList.remove('active');
                s.classList.add('completed');
            });

            setTimeout(() => {
                workflowCard.classList.remove('active');
                resultsCard.classList.add('active');

                document.getElementById('statPapers').textContent = stats.total_papers || 0;
                document.getElementById('statSessions').textContent = stats.total_sessions || 0;
                document.getElementById('statHighRelevance').textContent = stats.high_relevance || 0;
                document.getElementById('statAuthors').textContent = stats.enriched_authors || 0;
                document.getElementById('statEnrichedPapers').textContent = stats.enriched_papers || 0;

                const downloadBtn = document.getElementById('downloadBtn');
                downloadBtn.href = `/api/download/${sessionId}`;

                const openWebsiteBtn = document.getElementById('openWebsiteBtn');
                if (stats.website_file) {
                    openWebsiteBtn.href = `/api/website/${sessionId}`;
                    openWebsiteBtn.style.display = 'inline-block';
                } else {
                    openWebsiteBtn.style.display = 'none';
                }
            }, 500);
        }

        function restart() {
            resultsCard.classList.remove('active');
            workflowCard.classList.remove('active');
            setupCard.style.display = 'block';
            conferenceSelect.value = '';
            startBtn.disabled = true;
        }
    </script>

    <p style="text-align:center; color:#7a7a7a; font-size:0.85rem; margin-top:30px; max-width:800px; margin-left:auto; margin-right:auto;">
        <a href="https://www.github.com/aldro61/PaperAtlas/" target="_blank" style="color:#60a5fa;">PaperAtlas</a> is an independent project by <a href="https://alexdrouin.com" target="_blank" style="color:#60a5fa;">Alexandre Drouin</a>. We are not affiliated with <a href="https://scholar-inbox.com"  target="_blank" style="color:#60a5fa;">Scholar Inbox</a> and are grateful for their paper recommendation service that powers this app.
    </p>
</body>
</html>
'''


class ExtractionSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.status = 'running'
        self.current_step = None
        self.completed_steps = []
        self.step_detail = ''
        self.logs = []
        self.log_index = 0
        self.stats = {}
        self.output_file = None
        self.website_file = None
        self.error = None

    def log(self, message, log_type='info'):
        self.logs.append({'message': message, 'type': log_type})

    def get_new_logs(self):
        new_logs = self.logs[self.log_index:]
        self.log_index = len(self.logs)
        return new_logs


sessions = {}


def conference_file_stem(conference_name):
    """Build a filesystem-friendly stem like 'neurips2025' from a conference label."""
    if not conference_name:
        return 'conference'

    normalized = conference_name.replace('–', '-').replace('—', '-')
    left_part = normalized.split('-', 1)[0].strip()
    cleaned = ''.join(ch for ch in left_part.lower() if ch.isalnum())
    return cleaned or 'conference'


def build_output_files(conference_name):
    """Return consistent filenames for papers/authors/enriched papers/website."""
    stem = conference_file_stem(conference_name)
    return {
        'stem': stem,
        'papers': f'{stem}_papers.csv',
        'authors': f'{stem}_enriched_authors.json',
        'enriched_papers': f'{stem}_enriched_papers.json',
        'website': f'{stem}_website.html',
    }


def model_slug(model_id):
    """Return a safe slug for model IDs to embed in filenames."""
    if not model_id:
        return 'model'
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', model_id).strip('-').lower()
    return slug or 'model'


def clean_papers(papers):
    """Remove duplicate titles, drop low relevance, and scale scores to percentages."""
    seen_titles = set()
    cleaned = []
    dropped_dupes = 0
    dropped_low = 0

    for paper in papers:
        title = (paper.get('title') or '').strip()
        if not title:
            continue

        title_key = title.lower()
        if title_key in seen_titles:
            dropped_dupes += 1
            continue

        score_raw = paper.get('relevance_score', 0)
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = 0.0

        score_pct = round(score * 100, 2)
        if score_pct <= 50:
            dropped_low += 1
            continue

        cleaned_paper = paper.copy()
        cleaned_paper['title'] = title
        cleaned_paper['relevance_score'] = score_pct
        cleaned.append(cleaned_paper)
        seen_titles.add(title_key)

    return cleaned, dropped_dupes, dropped_low


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/check-dependencies', methods=['GET'])
def check_dependencies():
    """Check if required dependencies are installed."""
    openrouter_api = False
    playwright_installed = False
    conference_name = request.args.get('conference_name', '') or ''
    output_files = build_output_files(conference_name) if conference_name else {
        'papers': 'papers.csv',
        'authors': 'enriched_authors.json',
        'enriched_papers': 'papers_enriched_papers.json',
    }
    papers_exists = os.path.exists(output_files['papers'])
    authors_exists = os.path.exists(output_files['authors'])
    reuse_timestamp = None

    def get_mtime(path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    paper_mtime = get_mtime(output_files['papers']) if papers_exists else None
    author_mtime = get_mtime(output_files['authors']) if authors_exists else None
    if paper_mtime or author_mtime:
        mtimes = [t for t in [paper_mtime, author_mtime] if t]
        if mtimes:
            oldest = min(mtimes)
            reuse_timestamp = datetime.fromtimestamp(oldest).isoformat()

    # Check OpenRouter API key (reusing field name for UI)
    openrouter_api = OPENROUTER_API_KEY is not None

    # Check Playwright
    try:
        import playwright
        playwright_installed = True
    except ImportError:
        playwright_installed = False

    success = openrouter_api and playwright_installed

    return jsonify({
        'success': success,
        'openrouter_api': openrouter_api,
        'playwright': playwright_installed,
        'papers_exists': papers_exists,
        'authors_exists': authors_exists,
        'reuse_timestamp': reuse_timestamp,
    })


@app.route('/api/conferences', methods=['POST'])
def get_conferences():
    data = request.json
    login_link = data.get('login_link', '')

    async def fetch():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = await context.new_page()

            # Use secret login link
            await page.goto(login_link)
            await asyncio.sleep(3)

            # Fetch conferences
            response = await page.request.get(f"{API_BASE}/conference_list")
            if response.status != 200:
                await browser.close()
                return {'success': False, 'error': 'Failed to fetch conferences'}

            data = await response.json()
            await browser.close()

            if not data.get('success'):
                return {'success': False, 'error': 'API error'}

            return {'success': True, 'conferences': data.get('conferences', [])}

    try:
        result = asyncio.run(fetch())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/extract', methods=['POST'])
def start_extraction():
    data = request.json
    login_link = data.get('login_link')
    conference = data.get('conference')
    conference_name = data.get('conference_name') or ''
    output_files = build_output_files(conference_name)
    # Backward compatibility: allow explicit output_file override when no conference name is provided
    provided_output = data.get('output_file')
    if provided_output and not conference_name:
        output_files['papers'] = provided_output
        output_files['authors'] = provided_output.replace('.csv', '_enriched_authors.json')
        output_files['enriched_papers'] = provided_output.replace('.csv', '_enriched_papers.json')

    output_file = output_files['papers']
    reuse_existing = bool(data.get('reuse_existing'))

    # Model selections (with defaults)
    model_config = {
        'author_model': data.get('author_model') or 'openai/gpt-5-mini',
        'paper_model': data.get('paper_model') or 'openai/gpt-5-mini',
        'synthesis_model': data.get('synthesis_model') or 'openai/gpt-5',
    }

    session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    session = ExtractionSession(session_id)
    session.output_file = output_file
    sessions[session_id] = session

    # Run extraction in background thread
    thread = threading.Thread(
        target=run_extraction,
        args=(session, login_link, conference, conference_name, output_files, reuse_existing, model_config)
    )
    thread.start()

    return jsonify({'session_id': session_id})


def run_extraction(session, login_link, conference, conference_name, output_files, reuse_existing, model_config):
    asyncio.run(extract_papers(session, login_link, conference, conference_name, output_files, reuse_existing, model_config))


async def extract_papers(session, login_link, conference, conference_name, output_files, reuse_existing, model_config):
    output_file = output_files['papers']
    authors_file = output_files['authors']
    cleaned_papers = None
    sessions_list = []
    existing_enriched = {}  # Will be populated if existing enriched authors are found
    previously_attempted = {}  # Authors previously attempted but returned Unknown values
    conf_title = (conference_name.split(' - ')[0].strip() if conference_name else None) or conference

    def ensure_step(name):
        if name not in session.completed_steps:
            session.completed_steps.append(name)

    def load_existing_papers(path):
        loaded = []
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                paper = dict(row)
                try:
                    paper['relevance_score'] = float(row.get('relevance_score', 0))
                except (TypeError, ValueError):
                    paper['relevance_score'] = 0.0
                for bool_field in ['award', 'bookmarked', 'liked', 'disliked', 'pinned']:
                    val = row.get(bool_field, False)
                    paper[bool_field] = str(val).lower() in ('true', '1', 'yes', 'y')
                loaded.append(paper)
        return loaded

    # Reuse existing papers/authors if requested
    if reuse_existing and os.path.exists(output_file):
        session.log(f'Reusing existing papers from {output_file}')
        cleaned_papers = load_existing_papers(output_file)
        ensure_step('login')
        ensure_step('sessions')
        ensure_step('papers')
        ensure_step('save')

        session_ids = {p.get('session_id') or p.get('session_name') for p in cleaned_papers if p.get('session_id') or p.get('session_name')}
        scores = [p['relevance_score'] for p in cleaned_papers if isinstance(p.get('relevance_score'), (int, float))]
        high_relevance = sum(1 for s in scores if s >= HIGHLY_RELEVANT_THRESHOLD)
        session.stats = {
            'total_papers': len(cleaned_papers),
            'total_sessions': len(session_ids),
            'high_relevance': high_relevance,
        }

        session.current_step = 'authors'

        # Load existing enriched authors if available (for partial reuse)
        existing_enriched = {}
        previously_attempted = {}  # Authors that were attempted but returned Unknown
        if os.path.exists(authors_file):
            try:
                with open(authors_file, 'r', encoding='utf-8') as f:
                    existing_authors = json.load(f)
                # Create lookup by name - track both successful and attempted enrichments
                for author in existing_authors:
                    # Check if author has all required fields (was previously processed)
                    has_required_fields = all(
                        field in author for field in ['affiliation', 'role', 'photo_url', 'profile_url']
                    )
                    if not has_required_fields:
                        continue  # Skip incomplete entries

                    has_info = (
                        author.get('affiliation') and
                        author.get('affiliation') != 'Unknown' and
                        author.get('role') and
                        author.get('role') != 'Unknown'
                    )
                    if has_info:
                        existing_enriched[author['name']] = author
                    else:
                        # Author was previously attempted but returned Unknown values
                        previously_attempted[author['name']] = author
                session.log(f'Found {len(existing_enriched)} fully enriched authors from previous run')
                if previously_attempted:
                    session.log(f'Found {len(previously_attempted)} authors previously attempted but unresolved (will skip)')
            except Exception as reuse_err:
                session.log(f'Could not load existing authors file: {reuse_err}', 'warning')
        else:
            session.log('No existing author enrichment file found; will enrich all key authors')
    elif reuse_existing:
        session.log(f'Reuse requested but no papers file found at {output_file}; performing fresh extraction', 'warning')

    try:
        if cleaned_papers is None:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                )
                page = await context.new_page()

                # Step 1: Login
                session.current_step = 'login'
                session.log('Opening Scholar Inbox...')

                await page.goto(login_link)
                await asyncio.sleep(3)

                session.log('Logged in successfully', 'success')
                ensure_step('login')

                # Step 2: Get conference info and sessions
                session.current_step = 'sessions'
                session.log(f'Fetching conference: {conference}')

                # Get conference ID
                response = await page.request.get(f"{API_BASE}/conference_list")
                data = await response.json()

                conf_id = None
                conf_title = conference
                for conf in data.get('conferences', []):
                    if conf.get('conference_url') == conference:
                        conf_id = conf.get('conference_id')
                        conf_title = conf.get('short_title')
                        break

                if not conf_id:
                    raise Exception(f'Conference {conference} not found')

                session.log(f'Found: {conf_title} (ID: {conf_id})')

                # Get sessions
                response = await page.request.get(f"{API_BASE}/conference/{conf_id}/sessions")
                data = await response.json()

                sessions_list = []
                for day in data.get('conference_dates', []):
                    for event in day.get('events', []):
                        sessions_list.append({
                            'session_id': event.get('event_id'),
                            'session_name': event.get('session_name'),
                            'number_of_posters': event.get('number_of_posters', 0),
                        })

                total_expected = sum(s['number_of_posters'] for s in sessions_list)
                session.log(f'Found {len(sessions_list)} sessions with {total_expected} papers', 'success')
                ensure_step('sessions')

                # Step 3: Extract papers
                session.current_step = 'papers'
                all_papers = []

                for i, sess in enumerate(sessions_list):
                    session.step_detail = f'Session {i+1}/{len(sessions_list)}: {sess["session_name"]}'

                    response = await page.request.get(
                        f"{API_BASE}/conference/get_all_posters?session_id={sess['session_id']}"
                    )
                    data = await response.json()

                    posters = data.get('posters', []) + data.get('pinned_posters', [])

                    for poster in posters:
                        paper = {
                            'paper_id': poster.get('paper_id'),
                            'title': poster.get('poster_title', ''),
                            'authors': poster.get('poster_authors', ''),
                            'pdf_url': poster.get('paper_link', ''),
                            'session_id': sess['session_id'],
                            'session_name': sess['session_name'],
                            'poster_id': poster.get('poster_id', ''),
                            'poster_number': poster.get('poster_number', ''),
                            'tag': poster.get('tag', ''),
                            'relevance_score': poster.get('poster_relevance', 0),
                            'award': poster.get('award', False),
                            'bookmarked': poster.get('bookmarked', False),
                            'liked': poster.get('liked', False),
                            'disliked': poster.get('disliked', False),
                            'pinned': poster.get('pinned', False),
                        }
                        all_papers.append(paper)

                    if len(posters) > 0:
                        session.log(f'{sess["session_name"]}: {len(posters)} papers')

                    await asyncio.sleep(0.1)

                session.log(f'Extracted {len(all_papers)} papers total', 'success')
                ensure_step('papers')

                # Step 4: Save
                session.current_step = 'save'
                session.log(f'Saving to {output_file}...')

                cleaned_papers, dropped_dupes, dropped_low = clean_papers(all_papers)
                session.log(f'Filtered out {dropped_dupes} duplicate titles and {dropped_low} low-relevance papers')

                fieldnames = [
                    'paper_id', 'title', 'authors', 'pdf_url', 'session_id', 'session_name',
                    'poster_id', 'poster_number', 'tag', 'relevance_score',
                    'award', 'bookmarked', 'liked', 'disliked', 'pinned'
                ]

                with open(output_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(cleaned_papers)

                # Calculate stats
                scores = [p['relevance_score'] for p in cleaned_papers if p['relevance_score'] and p['relevance_score'] > 0]
                high_relevance = sum(1 for s in scores if s >= HIGHLY_RELEVANT_THRESHOLD)

                session.stats = {
                    'total_papers': len(cleaned_papers),
                    'total_sessions': len(sessions_list),
                    'high_relevance': high_relevance,
                }

                session.log(f'Saved {len(cleaned_papers)} papers to {output_file}', 'success')
                ensure_step('save')

                await browser.close()

        # Step 5: Enrich Authors (supports partial enrichment from previous runs)
        session.current_step = 'authors'
        session.log('Starting author enrichment...')

        # Load existing enriched authors only if reuse is enabled
        if reuse_existing and not existing_enriched and os.path.exists(authors_file):
            try:
                with open(authors_file, 'r', encoding='utf-8') as f:
                    existing_authors = json.load(f)
                for author in existing_authors:
                    # Check if author has all required fields (was previously processed)
                    has_required_fields = all(
                        field in author for field in ['affiliation', 'role', 'photo_url', 'profile_url']
                    )
                    if not has_required_fields:
                        continue  # Skip incomplete entries

                    has_info = (
                        author.get('affiliation') and
                        author.get('affiliation') != 'Unknown' and
                        author.get('role') and
                        author.get('role') != 'Unknown'
                    )
                    if has_info:
                        existing_enriched[author['name']] = author
                    else:
                        # Author was previously attempted but returned Unknown values
                        previously_attempted[author['name']] = author
                session.log(f'Found {len(existing_enriched)} fully enriched authors from previous run')
                if previously_attempted:
                    session.log(f'Found {len(previously_attempted)} authors previously attempted but unresolved (will skip)')
            except Exception as load_err:
                session.log(f'Could not load existing authors file: {load_err}', 'warning')

        try:
            # Initialize OpenRouter agent with selected model
            openrouter_agent = OpenRouterAuthorEnrichmentAgent(model=model_config['author_model'])
            session.log(f'Using OpenRouter model for authors: {openrouter_agent.model}')

            # Analyze authors from cleaned papers
            author_stats = analyze_authors(cleaned_papers, first_last_only=True)

            # Filter to authors with highly relevant papers
            key_authors = [a for a in author_stats if a['highly_relevant_count'] > 0]

            session.log(f'Found {len(key_authors)} key authors with highly relevant papers')

            # Separate already-enriched authors from those needing enrichment
            already_enriched_authors = []
            skipped_not_found_authors = []  # Authors previously attempted but returned Unknown
            authors_to_enrich = []

            for author in key_authors:
                if author['name'] in existing_enriched:
                    # Use existing enrichment data (successful enrichment)
                    existing = existing_enriched[author['name']]
                    author['affiliation'] = existing.get('affiliation', 'Unknown')
                    author['role'] = existing.get('role', 'Unknown')
                    author['photo_url'] = existing.get('photo_url')
                    author['profile_url'] = existing.get('profile_url')
                    already_enriched_authors.append(author)
                elif author['name'] in previously_attempted:
                    # Author was previously attempted but returned Unknown values - skip
                    existing = previously_attempted[author['name']]
                    author['affiliation'] = existing.get('affiliation', 'Unknown')
                    author['role'] = existing.get('role', 'Unknown')
                    author['photo_url'] = existing.get('photo_url')
                    author['profile_url'] = existing.get('profile_url')
                    skipped_not_found_authors.append(author)
                else:
                    authors_to_enrich.append(author)

            session.log(f'✓ {len(already_enriched_authors)} authors already enriched (reusing)')
            if skipped_not_found_authors:
                session.log(f'⏭ {len(skipped_not_found_authors)} authors previously attempted but unresolved (skipping)')
            session.log(f'→ {len(authors_to_enrich)} authors need enrichment')

            # If all authors are already enriched, skip to saving
            if len(authors_to_enrich) == 0:
                session.log('All key authors already enriched!', 'success')
                # Save both successful and not-found authors to preserve state
                all_processed_authors = already_enriched_authors + skipped_not_found_authors
                with open(authors_file, 'w', encoding='utf-8') as f:
                    json.dump(all_processed_authors, f, indent=2, ensure_ascii=False)
                session.log(f'Saved {len(all_processed_authors)} enriched authors to {authors_file}', 'success')
                ensure_step('authors')
                session.stats['enriched_authors'] = len(all_processed_authors)
            else:
                # Enrich missing authors in parallel using ThreadPoolExecutor
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import threading

                newly_enriched_authors = []
                completed_count = 0
                lock = threading.Lock()

                def enrich_single_author(author_data):
                    """Enrich a single author and return the enriched data."""
                    author = author_data.copy()
                    paper_titles = [p['title'] for p in author['papers']]
                    author_info = openrouter_agent.get_author_info(author['name'], paper_titles)

                    if author_info:
                        author['affiliation'] = author_info.get('affiliation', 'Unknown')
                        author['role'] = author_info.get('role', 'Unknown')
                        author['photo_url'] = author_info.get('photo_url', None)
                        author['profile_url'] = author_info.get('profile_url', None)
                        return author, True
                    else:
                        author['affiliation'] = 'Unknown'
                        author['role'] = 'Unknown'
                        author['photo_url'] = None
                        author['profile_url'] = None
                        return author, False

                # Process authors in parallel (OpenRouter handles web search server-side)
                session.log(f'Processing {len(authors_to_enrich)} authors with {AUTHOR_ENRICHMENT_WORKERS} parallel workers')
                with ThreadPoolExecutor(max_workers=AUTHOR_ENRICHMENT_WORKERS) as executor:
                    future_to_author = {executor.submit(enrich_single_author, author): author for author in authors_to_enrich}

                    for future in as_completed(future_to_author):
                        with lock:
                            completed_count += 1
                            session.step_detail = f'Enriching authors: {completed_count}/{len(authors_to_enrich)} completed'

                        try:
                            enriched_author, found_info = future.result()

                            with lock:
                                newly_enriched_authors.append(enriched_author)
                                if found_info:
                                    session.log(f'✓ [{completed_count}/{len(authors_to_enrich)}] {enriched_author["name"]} - {enriched_author["affiliation"]}, {enriched_author["role"]}')
                                else:
                                    session.log(f'⚠ [{completed_count}/{len(authors_to_enrich)}] {enriched_author["name"]} - No information found')

                        except Exception as e:
                            original_author = future_to_author[future]
                            with lock:
                                session.log(f'✗ [{completed_count}/{len(authors_to_enrich)}] {original_author["name"]} - Error: {str(e)}')

                # Combine already-enriched, skipped (not-found), and newly-enriched authors
                all_enriched_authors = already_enriched_authors + skipped_not_found_authors + newly_enriched_authors

                # Save enriched authors
                with open(authors_file, 'w', encoding='utf-8') as f:
                    json.dump(all_enriched_authors, f, indent=2, ensure_ascii=False)

                session.log(f'Saved {len(all_enriched_authors)} enriched authors to {authors_file} ({len(already_enriched_authors)} reused, {len(skipped_not_found_authors)} skipped, {len(newly_enriched_authors)} new)', 'success')
                ensure_step('authors')
                session.stats['enriched_authors'] = len(all_enriched_authors)

        except Exception as author_error:
            session.log(f'Author enrichment error: {str(author_error)}', 'warning')
            # Don't fail the whole extraction if author enrichment fails

        # Step 6: Enrich Papers (supports partial enrichment from previous runs)
        # Include model slug in filename for traceability (like synthesis files)
        papers_enrichment_file = os.path.join(
            os.path.dirname(output_file),
            f'{output_files["stem"]}_enriched_papers_{model_slug(model_config["paper_model"])}.json'
        )
        session.current_step = 'papers_enrichment'
        session.log('Starting paper enrichment...')

        # Required fields for a complete paper enrichment
        PAPER_REQUIRED_FIELDS = ['key_findings', 'description', 'key_contribution', 'novelty', 'ai_categories']

        # Load existing enriched papers only if reuse is enabled
        existing_enriched_papers = {}
        existing_categories = []
        if reuse_existing and os.path.exists(papers_enrichment_file):
            try:
                with open(papers_enrichment_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    existing_categories = existing_data.get('categories', [])
                    for paper in existing_data.get('papers', []):
                        is_complete = all(
                            field in paper and paper.get(field)
                            for field in PAPER_REQUIRED_FIELDS
                        )
                        if is_complete:
                            existing_enriched_papers[paper['title']] = paper
                session.log(f'Found {len(existing_enriched_papers)} fully enriched papers from previous run')
            except Exception as load_err:
                session.log(f'Could not load existing papers enrichment file: {load_err}', 'warning')

        try:
            # Initialize OpenRouter paper enrichment agent with selected model
            paper_agent = OpenRouterPaperEnrichmentAgent(model=model_config['paper_model'])
            session.log(f'Using model for paper enrichment: {paper_agent.model}')

            # Separate already-enriched papers from those needing enrichment
            already_enriched_papers = []
            papers_to_enrich = []

            for paper in cleaned_papers:
                title = paper['title']
                if title in existing_enriched_papers:
                    # Check if PDF URL changed
                    existing_pdf = existing_enriched_papers[title].get('pdf_url', '')
                    current_pdf = paper.get('pdf_url', '')
                    if existing_pdf == current_pdf:
                        # Merge existing enrichment with current paper data
                        enriched = paper.copy()
                        existing = existing_enriched_papers[title]
                        enriched['key_findings'] = existing.get('key_findings', '')
                        enriched['description'] = existing.get('description', '')
                        enriched['key_contribution'] = existing.get('key_contribution', '')
                        enriched['novelty'] = existing.get('novelty', '')
                        enriched['ai_categories'] = existing.get('ai_categories', [])
                        already_enriched_papers.append(enriched)
                    else:
                        papers_to_enrich.append(paper)
                else:
                    papers_to_enrich.append(paper)

            session.log(f'✓ {len(already_enriched_papers)} papers already enriched (reusing)')
            session.log(f'→ {len(papers_to_enrich)} papers need enrichment')

            # Generate or reuse categories
            if existing_categories and len(papers_to_enrich) < len(cleaned_papers) * 0.5:
                session.log(f'Reusing existing {len(existing_categories)} categories')
                categories = existing_categories
            else:
                session.log('Generating categories from paper titles...')
                categories = paper_agent.generate_categories(cleaned_papers)
                session.log(f'Generated {len(categories)} categories: {", ".join(categories[:5])}{"..." if len(categories) > 5 else ""}')

            if len(papers_to_enrich) == 0:
                session.log('All papers already enriched!', 'success')
                output_data = {
                    'categories': categories,
                    'papers': already_enriched_papers
                }
                with open(papers_enrichment_file, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)
                session.log(f'Saved {len(already_enriched_papers)} enriched papers to {papers_enrichment_file}', 'success')
                ensure_step('papers_enrichment')
                session.stats['enriched_papers'] = len(already_enriched_papers)
            else:
                # Enrich missing papers in parallel
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import threading

                newly_enriched_papers = []
                completed_count = 0
                lock = threading.Lock()

                def enrich_single_paper(paper_data, idx, total):
                    """Enrich a single paper and return the enriched data."""
                    paper = paper_data.copy()
                    title = paper['title']
                    pdf_url = paper.get('pdf_url', '')
                    score = paper.get('relevance_score', paper.get('score'))

                    try:
                        enrichment = paper_agent.enrich_paper(
                            title=title,
                            pdf_url=pdf_url if pdf_url else None,
                            categories=categories,
                            score=int(score) if score else None
                        )

                        if enrichment:
                            paper['key_findings'] = enrichment.get('key_findings', '')
                            paper['description'] = enrichment.get('description', '')
                            paper['key_contribution'] = enrichment.get('key_contribution', '')
                            paper['novelty'] = enrichment.get('novelty', '')
                            paper['ai_categories'] = enrichment.get('categories', [])
                            return paper, True
                        else:
                            paper['key_findings'] = ''
                            paper['description'] = ''
                            paper['key_contribution'] = ''
                            paper['novelty'] = ''
                            paper['ai_categories'] = []
                            return paper, False
                    except Exception as e:
                        paper['key_findings'] = ''
                        paper['description'] = ''
                        paper['key_contribution'] = ''
                        paper['novelty'] = ''
                        paper['ai_categories'] = []
                        return paper, False

                # Process papers in parallel (fewer workers than authors since PDF fetching is slower)
                session.log(f'Processing {len(papers_to_enrich)} papers with {PAPER_ENRICHMENT_WORKERS} parallel workers')

                def save_progress():
                    """Save current progress to file."""
                    all_papers = already_enriched_papers + newly_enriched_papers
                    output_data = {
                        'categories': categories,
                        'papers': all_papers
                    }
                    with open(papers_enrichment_file, 'w', encoding='utf-8') as f:
                        json.dump(output_data, f, indent=2, ensure_ascii=False)

                with ThreadPoolExecutor(max_workers=PAPER_ENRICHMENT_WORKERS) as executor:
                    future_to_paper = {
                        executor.submit(enrich_single_paper, paper, i + 1, len(papers_to_enrich)): paper
                        for i, paper in enumerate(papers_to_enrich)
                    }

                    for future in as_completed(future_to_paper):
                        with lock:
                            completed_count += 1
                            session.step_detail = f'Enriching papers: {completed_count}/{len(papers_to_enrich)} completed'

                        try:
                            enriched_paper, found_info = future.result()

                            with lock:
                                newly_enriched_papers.append(enriched_paper)
                                if found_info:
                                    cats = enriched_paper.get('ai_categories', [])
                                    session.log(f'✓ [{completed_count}/{len(papers_to_enrich)}] {enriched_paper["title"][:50]}... - {", ".join(cats[:2])}')
                                else:
                                    session.log(f'⚠ [{completed_count}/{len(papers_to_enrich)}] {enriched_paper["title"][:50]}... - No enrichment data')

                                # Save progress every 10 papers
                                if completed_count % 10 == 0:
                                    save_progress()
                                    session.log(f'💾 Progress saved: {completed_count}/{len(papers_to_enrich)}')

                        except Exception as e:
                            original_paper = future_to_paper[future]
                            with lock:
                                session.log(f'✗ [{completed_count}/{len(papers_to_enrich)}] {original_paper["title"][:50]}... - Error: {str(e)}')

                # Final save
                save_progress()

                session.log(f'Saved {len(already_enriched_papers) + len(newly_enriched_papers)} enriched papers to {papers_enrichment_file} ({len(already_enriched_papers)} reused, {len(newly_enriched_papers)} new)', 'success')
                ensure_step('papers_enrichment')
                session.stats['enriched_papers'] = len(already_enriched_papers) + len(newly_enriched_papers)

        except Exception as paper_error:
            session.log(f'Paper enrichment error: {str(paper_error)}', 'warning')
            # Don't fail the whole extraction if paper enrichment fails

        # Step 7: Generate Synthesis (optional but preferred when enriched papers exist)
        synthesis_html_file = os.path.join(
            os.path.dirname(output_file),
            f'{output_files["stem"]}_synthesis_{model_slug(model_config["synthesis_model"])}.html'
        )
        session.current_step = 'synthesis'
        session.log(f'Generating conference synthesis with {model_config["synthesis_model"]}...')

        try:
            # Reuse synthesis when reusing results and the matching file already exists
            if reuse_existing and os.path.exists(synthesis_html_file):
                session.log(f'Reusing existing synthesis: {synthesis_html_file}')
                ensure_step('synthesis')
                session.stats['synthesis_file'] = synthesis_html_file
                session.stats['synthesis_generated'] = True
            elif os.path.exists(papers_enrichment_file):
                if reuse_existing:
                    session.log(f'No synthesis file found for reuse; regenerating with {model_config["synthesis_model"]}')

                with open(papers_enrichment_file, 'r', encoding='utf-8') as f:
                    enriched_payload = json.load(f)
                enriched_papers = enriched_payload.get('papers', [])
                enriched_categories = enriched_payload.get('categories', [])

                if enriched_papers:
                    synthesis_html, _ = generate_synthesis(
                        papers=enriched_papers,
                        categories=enriched_categories,
                        model=model_config['synthesis_model'],
                        debug=False,
                        conference_name=conf_title or conference_name or ''
                    )

                    if synthesis_html:
                        with open(synthesis_html_file, 'w', encoding='utf-8') as f:
                            f.write(synthesis_html)
                        session.log(f'Saved synthesis to {synthesis_html_file}', 'success')
                        ensure_step('synthesis')
                        session.stats['synthesis_file'] = synthesis_html_file
                        session.stats['synthesis_generated'] = True
                    else:
                        session.log('Synthesis generation returned empty; skipping', 'warning')
                        session.stats['synthesis_generated'] = False
                else:
                    session.log('No enriched papers available; skipping synthesis generation', 'warning')
                    session.stats['synthesis_generated'] = False
            else:
                session.log('No enriched papers found; skipping synthesis generation', 'warning')
                session.stats['synthesis_generated'] = False
        except Exception as synthesis_error:
            session.log(f'Synthesis generation error: {str(synthesis_error)}', 'warning')
            session.stats['synthesis_generated'] = False
            # Do not fail pipeline if synthesis fails
        finally:
            ensure_step('synthesis')

        # Step 8: Generate Website
        website_file = output_files['website']
        session.current_step = 'website'
        session.log('Generating interactive website...')

        try:
            # Parse conference title from the full name (e.g., "NeurIPS 2025 - Conference on Neural...")
            conf_title = conference_name.split(' - ')[0].strip() if conference_name else None
            generate_website(
                csv_file=output_file,
                output_file=website_file,
                enriched_authors_file=authors_file,
                enriched_papers_file=papers_enrichment_file,
                conference_title=conf_title,
                synthesis_file=synthesis_html_file
            )
            session.log(f'Generated website: {website_file}', 'success')
            ensure_step('website')
            session.website_file = website_file
            session.stats['website_file'] = website_file
        except Exception as website_error:
            session.log(f'Website generation error: {str(website_error)}', 'warning')
            # Don't fail the whole extraction if website generation fails

        session.status = 'completed'
    except Exception as e:
        session.status = 'error'
        session.error = str(e)
        session.log(f'Error: {str(e)}', 'error')


@app.route('/api/progress/<session_id>')
def get_progress(session_id):
    session = sessions.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    return jsonify({
        'status': session.status,
        'current_step': session.current_step,
        'completed_steps': session.completed_steps,
        'step_detail': session.step_detail,
        'new_logs': session.get_new_logs(),
        'stats': session.stats,
        'error': session.error,
    })


@app.route('/api/download/<session_id>')
def download_file(session_id):
    session = sessions.get(session_id)
    if not session or not session.output_file:
        return jsonify({'error': 'File not found'}), 404

    if os.path.exists(session.output_file):
        return send_file(
            session.output_file,
            as_attachment=True,
            download_name=session.output_file
        )
    return jsonify({'error': 'File not found'}), 404


@app.route('/api/website/<session_id>')
def serve_website(session_id):
    """Serve the generated website HTML."""
    session = sessions.get(session_id)
    if not session or not session.website_file:
        return jsonify({'error': 'Website not found'}), 404

    if os.path.exists(session.website_file):
        return send_file(
            session.website_file,
            mimetype='text/html'
        )
    return jsonify({'error': 'Website not found'}), 404


@app.route('/banner.png')
def banner():
    """Serve the banner image from the repo root."""
    if os.path.exists('banner.png'):
        return send_file('banner.png')
    return jsonify({'error': 'Banner not found'}), 404


if __name__ == '__main__':
    print("="*60)
    print("PaperAtlas Web UI")
    print("="*60)
    print("\nOpen http://localhost:5001 in your browser")
    print("Press Ctrl+C to stop the server\n")
    app.run(debug=False, port=5001)
