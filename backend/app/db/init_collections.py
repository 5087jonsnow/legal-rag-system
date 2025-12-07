# ============================================================
# FILE: backend/app/db/init_collections.py
# PURPOSE: Initialize Qdrant collections for dual corpus architecture
# ============================================================

"""
Initialize dual corpus Qdrant collections.

Collections:
1. public_legal_corpus - Shared SC/HC judgments, statutes
2. private_user_corpus - User-uploaded documents with org_id filtering

Run this script once during deployment or when collections need recreation.
"""

import asyncio
import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType, PayloadIndexParams

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CollectionInitializer:
    """Initialize Qdrant collections for legal RAG system"""

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        self.embedding_dim = settings.EMBEDDING_DIMENSION

    async def create_dual_corpus_collections(self, recreate: bool = False):
        """
        Create both public and private corpus collections.

        Args:
            recreate: If True, delete existing collections and recreate
        """
        logger.info("🚀 Initializing dual corpus collections...")

        # 1. Create public corpus
        await self._create_public_corpus(recreate=recreate)

        # 2. Create private corpus
        await self._create_private_corpus(recreate=recreate)

        logger.info("✅ Dual corpus collections initialized successfully!")

    async def _create_public_corpus(self, recreate: bool = False):
        """
        Create public legal corpus collection.

        Schema:
        - Vectors: Legal-BERT embeddings (768-dim)
        - Payload: citation, court, year, text, etc.
        - No access control (public to all users)
        """
        collection_name = "public_legal_corpus"

        # Delete if recreate flag set
        if recreate:
            try:
                self.client.delete_collection(collection_name)
                logger.info(f"🗑️  Deleted existing collection: {collection_name}")
            except Exception:
                pass  # Collection didn't exist

        # Check if exists
        collections = self.client.get_collections().collections
        if any(c.name == collection_name for c in collections):
            logger.info(f"✓ Collection already exists: {collection_name}")
            return

        # Create collection
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=self.embedding_dim,
                distance=Distance.COSINE
            )
        )

        # Create payload indexes for fast filtering
        # Index citation fields for verification
        self.client.create_payload_index(
            collection_name=collection_name,
            field_name="citation_air",
            field_schema=PayloadSchemaType.KEYWORD
        )

        self.client.create_payload_index(
            collection_name=collection_name,
            field_name="citation_scc",
            field_schema=PayloadSchemaType.KEYWORD
        )

        self.client.create_payload_index(
            collection_name=collection_name,
            field_name="court",
            field_schema=PayloadSchemaType.KEYWORD
        )

        self.client.create_payload_index(
            collection_name=collection_name,
            field_name="year",
            field_schema=PayloadSchemaType.INTEGER
        )

        logger.info(f"✅ Created public corpus collection: {collection_name}")
        logger.info(f"   - Vector dimension: {self.embedding_dim}")
        logger.info(f"   - Distance metric: COSINE")
        logger.info(f"   - Indexed fields: citation_air, citation_scc, court, year")

    async def _create_private_corpus(self, recreate: bool = False):
        """
        Create private user corpus collection.

        Schema:
        - Vectors: Legal-BERT embeddings (768-dim)
        - Payload: org_id (for filtering), uploaded_by, text, metadata
        - Access control: Filter by org_id
        """
        collection_name = "private_user_corpus"

        # Delete if recreate flag set
        if recreate:
            try:
                self.client.delete_collection(collection_name)
                logger.info(f"🗑️  Deleted existing collection: {collection_name}")
            except Exception:
                pass

        # Check if exists
        collections = self.client.get_collections().collections
        if any(c.name == collection_name for c in collections):
            logger.info(f"✓ Collection already exists: {collection_name}")
            return

        # Create collection
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=self.embedding_dim,
                distance=Distance.COSINE
            )
        )

        # CRITICAL: Index org_id for fast filtering (multi-tenancy)
        self.client.create_payload_index(
            collection_name=collection_name,
            field_name="org_id",
            field_schema=PayloadSchemaType.KEYWORD
        )

        # Index uploaded_by for user document management
        self.client.create_payload_index(
            collection_name=collection_name,
            field_name="uploaded_by",
            field_schema=PayloadSchemaType.KEYWORD
        )

        # Index created_at for sorting
        self.client.create_payload_index(
            collection_name=collection_name,
            field_name="created_at",
            field_schema=PayloadSchemaType.KEYWORD
        )

        logger.info(f"✅ Created private corpus collection: {collection_name}")
        logger.info(f"   - Vector dimension: {self.embedding_dim}")
        logger.info(f"   - Distance metric: COSINE")
        logger.info(f"   - Indexed fields: org_id, uploaded_by, created_at")
        logger.info(f"   - Multi-tenancy: ENABLED (org_id filtering)")

    async def migrate_existing_data(
        self,
        source_collection: str = "legal_documents",
        target_collection: str = "public_legal_corpus"
    ):
        """
        Migrate existing data from single collection to dual corpus.

        Args:
            source_collection: Existing collection name
            target_collection: Target collection (usually public)
        """
        logger.info(f"📦 Migrating data: {source_collection} → {target_collection}")

        try:
            # Check if source exists
            collections = self.client.get_collections().collections
            if not any(c.name == source_collection for c in collections):
                logger.warning(f"Source collection '{source_collection}' not found. Skipping migration.")
                return

            # Scroll through source collection
            offset = None
            migrated_count = 0
            batch_size = 100

            while True:
                scroll_result = self.client.scroll(
                    collection_name=source_collection,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True
                )

                points, offset = scroll_result

                if not points:
                    break

                # Upsert to target collection
                self.client.upsert(
                    collection_name=target_collection,
                    points=points
                )

                migrated_count += len(points)
                logger.info(f"   Migrated {migrated_count} documents...")

                if offset is None:
                    break

            logger.info(f"✅ Migration complete: {migrated_count} documents migrated")

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}", exc_info=True)
            raise

    def get_collection_stats(self) -> dict:
        """Get statistics for all collections"""
        collections = self.client.get_collections().collections

        stats = {}
        for collection in collections:
            try:
                info = self.client.get_collection(collection.name)
                stats[collection.name] = {
                    "points_count": info.points_count,
                    "vectors_count": info.vectors_count,
                    "indexed_vectors_count": info.indexed_vectors_count,
                    "status": info.status
                }
            except Exception as e:
                stats[collection.name] = {"error": str(e)}

        return stats


async def main():
    """Main initialization function"""
    import argparse

    parser = argparse.ArgumentParser(description="Initialize Qdrant collections")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate existing collections"
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Migrate data from old 'legal_documents' collection"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show collection statistics"
    )

    args = parser.parse_args()

    initializer = CollectionInitializer()

    # Create collections
    if not args.stats:
        await initializer.create_dual_corpus_collections(recreate=args.recreate)

    # Migrate existing data
    if args.migrate:
        await initializer.migrate_existing_data(
            source_collection="legal_documents",
            target_collection="public_legal_corpus"
        )

    # Show stats
    if args.stats or args.migrate:
        logger.info("\n📊 Collection Statistics:")
        stats = initializer.get_collection_stats()
        for name, info in stats.items():
            logger.info(f"\n{name}:")
            for key, value in info.items():
                logger.info(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())


# End of file
