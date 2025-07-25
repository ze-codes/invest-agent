# InvestAgent

An AI-powered investment research assistant.

## MVP Scope

The goal of the MVP is to tackle the most critical manual inefficiencies in investment research.

- **AI Chat Interface:** A primary interface where users can interact with the AI, featuring a project view.
- **One-Click Document Analysis:** The ability for the user to provide a URL or upload a PDF whitepaper. The system will then extract the text, process it, and make it available for querying through the chat.
- **Real-time Market Data:** API integration with a price aggregator like CoinGecko to provide accurate, real-time data such as price, market cap, and trading volume in AI responses.
- **Basic Personalization:** The app will ask users optional questions about their risk tolerance to help the AI frame its analysis and suggestions.
- **Source Citation:** All AI-generated answers must include their data sources to ensure credibility and build user trust.

## Tech Stack

- **Frontend:** Streamlit
- **Backend & Orchestration:** n8n (Cloud version)
- **Data Sources:** CoinGecko API, PDF/URL document analysis.
