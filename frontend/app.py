import streamlit as st
import requests
import os
from datetime import datetime

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")
API_V1 = f"{BACKEND_URL}/api/v1"

# Page config
st.set_page_config(
    page_title="Legal RAG System",
    page_icon="⚖️",
    layout="wide",
)

# Title
st.title("⚖️ Legal RAG System")
st.markdown("*AI-Powered Legal Research for Indian Law*")

# Sidebar
with st.sidebar:
    st.header("Navigation")
    page = st.radio(
        "Select Page",
        ["🔍 Search", "📄 Upload Documents", "📊 Analytics"]
    )
    
    st.markdown("---")
    st.markdown("### About")
    st.markdown("""
    This system uses advanced AI to help you:
    - Search case law and statutes
    - Get instant answers to legal questions
    - Upload and organize legal documents
    
    **Hybrid Architecture:**
    - Cognita: Document parsing
    - Custom: Legal intelligence
    """)

# Search Page
if page == "🔍 Search":
    st.header("Legal Research")
    
    # Search input
    query = st.text_area(
        "Enter your legal question:",
        placeholder="e.g., What is the latest Supreme Court position on anticipatory bail?",
        height=100
    )
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        top_k = st.slider("Number of results", 1, 20, 5)
    with col2:
        include_answer = st.checkbox("Generate AI Answer", value=True)
    with col3:
        court_filter = st.selectbox(
            "Court",
            ["All Courts", "Supreme Court", "High Court"]
        )
    
    # Search button
    if st.button("🔍 Search", type="primary"):
        if not query:
            st.warning("Please enter a search query")
        else:
            with st.spinner("Searching legal database..."):
                try:
                    # Prepare filters
                    filters = {}
                    if court_filter != "All Courts":
                        filters["court_level"] = court_filter
                    
                    # Make API request
                    response = requests.post(
                        f"{API_V1}/search/",
                        json={
                            "query": query,
                            "top_k": top_k,
                            "filters": filters if filters else None,
                            "include_answer": include_answer
                        },
                        timeout=60
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Display answer
                        if data.get("answer"):
                            st.success("### AI-Generated Answer")
                            st.markdown(data["answer"])
                            
                            # Citations
                            if data.get("citations"):
                                with st.expander("📚 Citations Used"):
                                    for cite in data["citations"]:
                                        st.markdown(f"**[{cite['index']}]** {cite.get('citation', 'Unknown')}")
                        
                        # Display search results
                        st.markdown("---")
                        st.subheader(f"📄 Search Results ({data['num_results']})")
                        st.caption(f"⚡ Search completed in {data['latency_ms']}ms")
                        
                        for i, result in enumerate(data["results"], 1):
                            with st.expander(f"**Result {i}** - Score: {result['score']:.3f}"):
                                metadata = result.get("metadata", {})
                                
                                # Show metadata
                                cols = st.columns(3)
                                with cols[0]:
                                    st.metric("Citation", metadata.get("citation", "N/A"))
                                with cols[1]:
                                    st.metric("Court", metadata.get("court_name", "N/A"))
                                with cols[2]:
                                    st.metric("Date", metadata.get("decision_date", "N/A"))
                                
                                # Show text
                                st.markdown("**Text:**")
                                st.text(result["text"][:500] + "..." if len(result["text"]) > 500 else result["text"])
                    
                    else:
                        st.error(f"Search failed: {response.text}")
                
                except requests.exceptions.Timeout:
                    st.error("⏱️ Request timed out. Try a simpler query.")
                except requests.exceptions.ConnectionError:
                    st.error("🔌 Cannot connect to backend. Is it running?")
                    st.code("docker-compose up -d")
                except Exception as e:
                    st.error(f"Error: {e}")

# Upload Page
elif page == "📄 Upload Documents":
    st.header("Upload Legal Documents")
    
    st.markdown("""
    Upload PDF documents to add them to your legal knowledge base.
    
    **Supported document types:**
    - 📋 Court Judgments
    - 📜 Statutes and Acts
    - 📝 Legal Contracts
    - 📑 Legal Precedents
    
    **What happens:**
    1. Cognita parses your PDF
    2. We extract legal metadata (citations, courts, judges)
    3. Document is indexed and ready for search
    """)
    
    # File uploader
    uploaded_files = st.file_uploader(
        "Choose PDF files",
        type=["pdf"],
        accept_multiple_files=True
    )
    
    document_type = st.selectbox(
        "Document Type",
        ["judgment", "statute", "contract", "precedent"]
    )
    
    if st.button("📤 Upload", type="primary"):
        if not uploaded_files:
            st.warning("Please select files to upload")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Uploading {uploaded_file.name}...")
                
                try:
                    files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
                    data = {"document_type": document_type}
                    
                    response = requests.post(
                        f"{API_V1}/upload/document",
                        files=files,
                        data=data,
                        timeout=120
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"✅ {uploaded_file.name} - {result['message']}")
                    else:
                        st.error(f"❌ {uploaded_file.name} - Upload failed: {response.text}")
                
                except Exception as e:
                    st.error(f"❌ {uploaded_file.name} - Error: {e}")
                
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            status_text.text("Upload complete!")
            st.info("Documents are being processed in the background. Check backend logs: `docker-compose logs -f backend`")

# Analytics Page
elif page == "📊 Analytics":
    st.header("Usage Analytics")
    
    try:
        response = requests.get(f"{API_V1}/analytics/", timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Queries", data.get("total_queries", 0))
            with col2:
                st.metric("Total Documents", data.get("total_documents", 0))
            with col3:
                st.metric("Avg Latency", f"{data.get('avg_query_latency_ms', 0):.0f}ms")
            with col4:
                st.metric("Success Rate", "N/A")
            
            # Coming soon
            st.info("📈 Detailed analytics dashboard coming soon!")
        else:
            st.error("Failed to load analytics")
    
    except requests.exceptions.ConnectionError:
        st.error("🔌 Cannot connect to backend")
        st.info("Make sure backend is running: `docker-compose up -d`")
    except Exception as e:
        st.error(f"Error: {e}")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Legal RAG System v0.1.0 | Built for Indian Legal Professionals</p>
        <p style='font-size: 0.8em'>Hybrid: Cognita (parsing) + Custom (legal intelligence)</p>
    </div>
    """,
    unsafe_allow_html=True
)