"""
Test LlamaIndex service locally (outside Docker)
Run from: backend/ directory
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variables for local testing
os.environ['QDRANT_HOST'] = 'localhost'
os.environ['QDRANT_PORT'] = '6333'

# Verify API key is loaded
if not os.getenv('GROQ_API_KEY'):
    print("❌ ERROR: GROQ_API_KEY not found in environment!")
    print("Make sure .env file exists with GROQ_API_KEY=your_key")
    sys.exit(1)

async def test_llamaindex():
    """Test LlamaIndex with your existing data"""
    
    print("=" * 70)
    print("🧪 TESTING LLAMAINDEX WITH YOUR LEGAL DATA")
    print("=" * 70)
    
    try:
        # Import service
        from app.services.llamaindex_service import get_llamaindex_rag
        
        # Get instance
        print("\n📦 Loading LlamaIndex service...")
        rag = get_llamaindex_rag()
        
        # Initialize
        print("🚀 Initializing...")
        rag.initialize()
        
        # Test query
        query = "What are the conditions for granting bail?"
        print(f"\n📝 Testing query: '{query}'")
        print("🔍 Searching and generating answer...\n")
        
        # Search
        result = await rag.search_and_answer(query, top_k=5)
        
        # Display results
        print("=" * 70)
        print("📊 RESULTS")
        print("=" * 70)
        
        print(f"\n✅ Engine: {result['engine']}")
        print(f"✅ Found {result['source_count']} sources")
        
        print(f"\n🤖 AI ANSWER:")
        print("-" * 70)
        print(result['answer'])
        print("-" * 70)
        
        print(f"\n📚 TOP SOURCES:")
        for i, source in enumerate(result['sources'][:3], 1):
            print(f"\n{i}. Similarity Score: {source['score']:.4f}")
            print(f"   Document: {source['metadata'].get('document_id', 'Unknown')}")
            print(f"   Text Preview: {source['text'][:150]}...")
        
        print("\n" + "=" * 70)
        print("✅ TEST PASSED - LLAMAINDEX WORKING!")
        print("=" * 70)
        
        # Compare with expected
        if result['source_count'] >= 3:
            print("\n✅ Quality Check: Retrieved sufficient sources")
        else:
            print("\n⚠️  Warning: Low number of sources")
        
        if len(result['answer']) > 100:
            print("✅ Quality Check: Answer is detailed")
        else:
            print("⚠️  Warning: Answer seems short")
        
        return True
        
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ TEST FAILED")
        print("=" * 70)
        print(f"\nError: {e}")
        
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()
        
        print("\n🔧 Troubleshooting:")
        print("1. Make sure Docker containers are running: docker-compose ps")
        print("2. Check Qdrant has data: http://localhost:6333/dashboard")
        print("3. Verify backend logs: docker-compose logs backend")
        print("4. Check .env file has GROQ_API_KEY")
        
        return False

if __name__ == "__main__":
    success = asyncio.run(test_llamaindex())
    sys.exit(0 if success else 1)