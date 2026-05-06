"""Document chunking strategies for RAG pipeline."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class ChunkingStrategy(str, Enum):
    FIXED_SIZE = "fixed_size"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    SEMANTIC = "semantic"
    RECURSIVE = "recursive"


@dataclass
class Chunk:
    """A single document chunk."""
    chunk_id: str
    content: str
    metadata: dict[str, Any]
    start_char: int
    end_char: int
    token_count: int


@dataclass
class ChunkingConfig:
    """Chunking configuration."""
    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 512
    chunk_overlap: int = 50
    separators: list[str] | None = None
    min_chunk_size: int = 50


class DocumentChunker:
    """Splits documents into chunks for embedding and retrieval."""

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()
        if self.config.separators is None:
            self.config.separators = ["\n\n", "\n", ". ", "! ", "? ", " ", ""]

    def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:
        """Split text into chunks using the configured strategy."""
        if not text:
            return []

        metadata = metadata or {}
        strategy = self.config.strategy

        if strategy == ChunkingStrategy.FIXED_SIZE:
            return self._chunk_fixed_size(text, metadata)
        elif strategy == ChunkingStrategy.SENTENCE:
            return self._chunk_sentence(text, metadata)
        elif strategy == ChunkingStrategy.PARAGRAPH:
            return self._chunk_paragraph(text, metadata)
        elif strategy == ChunkingStrategy.RECURSIVE:
            return self._chunk_recursive(text, metadata)
        elif strategy == ChunkingStrategy.SEMANTIC:
            return self._chunk_sentence(text, metadata)  # Fallback to sentence
        return self._chunk_recursive(text, metadata)

    def _chunk_fixed_size(self, text: str, metadata: dict[str, Any]) -> list[Chunk]:
        """Split text into fixed-size chunks with overlap."""
        chunks: list[Chunk] = []
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        start = 0
        idx = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_text = text[start:end]

            if len(chunk_text.strip()) >= self.config.min_chunk_size:
                chunks.append(Chunk(
                    chunk_id=f"{metadata.get('doc_id', 'doc')}_chunk_{idx}",
                    content=chunk_text,
                    metadata={**metadata, "chunk_index": idx},
                    start_char=start,
                    end_char=end,
                    token_count=self._estimate_tokens(chunk_text),
                ))
                idx += 1

            start = end - overlap if end < len(text) else end

        return chunks

    def _chunk_sentence(self, text: str, metadata: dict[str, Any]) -> list[Chunk]:
        """Split text by sentences, combining into chunks up to chunk_size."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks: list[Chunk] = []
        current_chunk: list[str] = []
        current_size = 0
        idx = 0
        start = 0

        for sentence in sentences:
            sentence_size = len(sentence)
            if current_size + sentence_size > self.config.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                if len(chunk_text.strip()) >= self.config.min_chunk_size:
                    chunks.append(Chunk(
                        chunk_id=f"{metadata.get('doc_id', 'doc')}_chunk_{idx}",
                        content=chunk_text,
                        metadata={**metadata, "chunk_index": idx},
                        start_char=start,
                        end_char=start + len(chunk_text),
                        token_count=self._estimate_tokens(chunk_text),
                    ))
                    idx += 1
                start += len(chunk_text) + 1
                current_chunk = []
                current_size = 0

            current_chunk.append(sentence)
            current_size += sentence_size

        # Last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            if len(chunk_text.strip()) >= self.config.min_chunk_size:
                chunks.append(Chunk(
                    chunk_id=f"{metadata.get('doc_id', 'doc')}_chunk_{idx}",
                    content=chunk_text,
                    metadata={**metadata, "chunk_index": idx},
                    start_char=start,
                    end_char=start + len(chunk_text),
                    token_count=self._estimate_tokens(chunk_text),
                ))

        return chunks

    def _chunk_paragraph(self, text: str, metadata: dict[str, Any]) -> list[Chunk]:
        """Split text by paragraphs, combining small ones."""
        paragraphs = text.split("\n\n")
        chunks: list[Chunk] = []
        current_chunk: list[str] = []
        current_size = 0
        idx = 0
        start = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if current_size + len(para) > self.config.chunk_size and current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                if len(chunk_text.strip()) >= self.config.min_chunk_size:
                    chunks.append(Chunk(
                        chunk_id=f"{metadata.get('doc_id', 'doc')}_chunk_{idx}",
                        content=chunk_text,
                        metadata={**metadata, "chunk_index": idx},
                        start_char=start,
                        end_char=start + len(chunk_text),
                        token_count=self._estimate_tokens(chunk_text),
                    ))
                    idx += 1
                start += len(chunk_text) + 2
                current_chunk = []
                current_size = 0

            current_chunk.append(para)
            current_size += len(para) + 2

        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            if len(chunk_text.strip()) >= self.config.min_chunk_size:
                chunks.append(Chunk(
                    chunk_id=f"{metadata.get('doc_id', 'doc')}_chunk_{idx}",
                    content=chunk_text,
                    metadata={**metadata, "chunk_index": idx},
                    start_char=start,
                    end_char=start + len(chunk_text),
                    token_count=self._estimate_tokens(chunk_text),
                ))

        return chunks

    def _chunk_recursive(self, text: str, metadata: dict[str, Any]) -> list[Chunk]:
        """Recursively split text using a hierarchy of separators."""
        separators = self.config.separators or ["\n\n", "\n", ". ", " ", ""]
        return self._recursive_split(text, separators, metadata, 0, 0)

    def _recursive_split(
        self,
        text: str,
        separators: list[str],
        metadata: dict[str, Any],
        start_offset: int,
        chunk_index: int,
    ) -> list[Chunk]:
        """Recursively split text by trying separators in order."""
        if len(text) <= self.config.chunk_size:
            if len(text.strip()) >= self.config.min_chunk_size:
                return [Chunk(
                    chunk_id=f"{metadata.get('doc_id', 'doc')}_chunk_{chunk_index}",
                    content=text,
                    metadata={**metadata, "chunk_index": chunk_index},
                    start_char=start_offset,
                    end_char=start_offset + len(text),
                    token_count=self._estimate_tokens(text),
                )]
            return []

        # Try each separator
        for sep in separators:
            parts = text.split(sep)
            if len(parts) <= 1:
                continue

            chunks: list[Chunk] = []
            current_parts: list[str] = []
            current_size = 0
            current_index = chunk_index
            offset = start_offset

            for part in parts:
                part_with_sep = part + sep if sep else part
                if current_size + len(part_with_sep) > self.config.chunk_size and current_parts:
                    chunk_text = sep.join(current_parts) if sep else "".join(current_parts)
                    if len(chunk_text.strip()) >= self.config.min_chunk_size:
                        chunks.extend(self._recursive_split(
                            chunk_text, separators[1:] if len(separators) > 1 else [""],
                            metadata, offset, current_index,
                        ))
                        current_index += len(chunks)
                    offset += len(chunk_text)
                    current_parts = []
                    current_size = 0

                current_parts.append(part)
                current_size += len(part_with_sep)

            # Last part
            if current_parts:
                chunk_text = sep.join(current_parts) if sep else "".join(current_parts)
                if len(chunk_text.strip()) >= self.config.min_chunk_size:
                    chunks.extend(self._recursive_split(
                        chunk_text, separators[1:] if len(separators) > 1 else [""],
                        metadata, offset, current_index,
                    ))

            return chunks

        # Fallback to fixed size
        return self._chunk_fixed_size(text, metadata)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token count estimate (words * 1.3)."""
        return int(len(text.split()) * 1.3)
