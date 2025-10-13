from typing import List, Dict, Any, Optional
import logging
from groq import Groq
from openai import OpenAI
import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting multiple providers"""
    
    def __init__(self):
        self.provider = settings.DEFAULT_LLM_PROVIDER
        self.model = settings.DEFAULT_LLM_MODEL
        
        # Initialize clients
        self.groq_client = None
        self.openai_client = None
        self.anthropic_client = None
        
        if settings.GROQ_API_KEY:
            self.groq_client = Groq(api_key=settings.GROQ_API_KEY)
            logger.info("✓ Groq client initialized")
        
        if settings.OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info("✓ OpenAI client initialized")
        
        if settings.ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            logger.info("✓ Anthropic client initialized")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = None,
        max_tokens: int = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Generate text completion
        
        Args:
            prompt: User prompt
            system_prompt: System message
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            provider: Override default provider
            model: Override default model
            
        Returns:
            Generated text
        """
        provider = provider or self.provider
        model = model or self.model
        temperature = temperature or settings.LLM_TEMPERATURE
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        
        try:
            if provider == "groq":
                return await self._generate_groq(
                    prompt, system_prompt, temperature, max_tokens, model
                )
            elif provider == "openai":
                return await self._generate_openai(
                    prompt, system_prompt, temperature, max_tokens, model
                )
            elif provider == "anthropic":
                return await self._generate_anthropic(
                    prompt, system_prompt, temperature, max_tokens, model
                )
            else:
                raise ValueError(f"Unknown provider: {provider}")
        
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise
    
    async def _generate_groq(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        model: str,
    ) -> str:
        """Generate with Groq"""
        if not self.groq_client:
            raise RuntimeError("Groq client not initialized")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = self.groq_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content
    
    async def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        model: str,
    ) -> str:
        """Generate with OpenAI"""
        if not self.openai_client:
            raise RuntimeError("OpenAI client not initialized")
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = self.openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content
    
    async def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        model: str,
    ) -> str:
        """Generate with Anthropic"""
        if not self.anthropic_client:
            raise RuntimeError("Anthropic client not initialized")
        
        response = self.anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt if system_prompt else "",
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text
    
    async def generate_with_context(
        self,
        query: str,
        context_docs: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate answer with retrieved context (RAG)
        
        Args:
            query: User query
            context_docs: Retrieved documents with text and metadata
            system_prompt: Optional system prompt
            
        Returns:
            Dict with answer and citations
        """
        # Build context from documents
        context_parts = []
        for i, doc in enumerate(context_docs, 1):
            text = doc.get("text", "")
            metadata = doc.get("metadata", {})
            citation = metadata.get("citation", f"Document {i}")
            
            context_parts.append(f"[{i}] {citation}\n{text}\n")
        
        context_str = "\n".join(context_parts)
        
        # Default system prompt for legal Q&A
        if not system_prompt:
            system_prompt = """You are a legal research assistant specialized in Indian law.
Your task is to answer questions based on the provided legal documents.

Guidelines:
1. Always cite your sources using [number] notation
2. Be precise and accurate with legal terminology
3. If the answer is not in the documents, say so
4. Do not make up information or hallucinate
5. Provide relevant case law and statutory references
6. Format your answer clearly with proper structure"""
        
        # Build prompt
        prompt = f"""Context documents:
{context_str}

Question: {query}

Please provide a comprehensive answer based on the context documents above. 
Include citations in your answer using [number] notation."""
        
        # Generate answer
        answer = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
        )
        
        # Extract citations used (simple parsing)
        citations = []
        for i, doc in enumerate(context_docs, 1):
            if f"[{i}]" in answer:
                metadata = doc.get("metadata", {})
                citations.append({
                    "index": i,
                    "citation": metadata.get("citation", ""),
                    "document_id": doc.get("id", ""),
                    "score": doc.get("score", 0.0),
                })
        
        return {
            "answer": answer,
            "citations": citations,
            "context_docs": context_docs,
        }


# Singleton instance
_llm_client = None


def get_llm_client() -> LLMClient:
    """Get LLM client singleton"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client