from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
import nest_asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dm_agent.rag.chunk import chunk_text
nest_asyncio.apply()
from huggingface_hub import snapshot_download
from milvus_model.hybrid import BGEM3EmbeddingFunction
from llama_cloud_services import LlamaParse
from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
)

parse = LlamaParse(
    api_key="llx-P70uVt1Sq1IsaQW8VZcr8AkB9ffzkCy8fPrqrodtT87MGUBc",
    result_type="markdown" if hasattr(LlamaParse, 'ResultType') else "markdown",
    num_workers=3,
    verbose=True,
    language="ch_sim",
)

file_extractor = {'.pdf': parse}
document_cloud = SimpleDirectoryReader(input_dir="/home/tianwenkai/workspace/DM-Code-Agent/dm_agent/data", file_extractor=file_extractor).load_data()


all_doc=''
for doc in document_cloud:
    all_doc+=doc.text

chunks = chunk_text(all_doc, 300)

snapshot_download("BAAI/bge-m3", local_dir="/home/tianwenkai/workspace/DM-Code-Agent/dm_agent/model", local_dir_use_symlinks=False)
ef = BGEM3EmbeddingFunction(model_name_or_path="/home/tianwenkai/workspace/DM-Code-Agent/dm_agent/model", use_fp16=False, device="cpu")
dense_dim = ef.dim["dense"]
# Generate embeddings using BGE-M3 model
chunks_embeddings = ef(chunks)
connections.connect(uri="./milvus.db")

fields = [
    # Use auto generated id as primary key
    FieldSchema(
        name="pk", dtype=DataType.VARCHAR, is_primary=True, auto_id=True, max_length=100
    ),
    # Store the original text to retrieve based on semantically distance
    FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=512),
    # Milvus now supports both sparse and dense vectors,
    # we can store each in a separate field to conduct hybrid search on both vectors
    FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
    FieldSchema(name="dense_vector", dtype=DataType.FLOAT_VECTOR, dim=dense_dim),
]
schema = CollectionSchema(fields)

col_name = "hybrid_demo"
if utility.has_collection(col_name):
    Collection(col_name).drop()
col = Collection(col_name, schema, consistency_level="Strong")

sparse_index = {"index_type": "SPARSE_INVERTED_INDEX", "metric_type": "IP"}
col.create_index("sparse_vector", sparse_index)
dense_index = {"index_type": "AUTOINDEX", "metric_type": "IP"}
col.create_index("dense_vector", dense_index)
col.load()

for i in range(len(chunks)):
    batched_entities = [
        chunks[i: i + 50],
        chunks_embeddings["sparse"][i: i + 50],
        chunks_embeddings["dense"][i: i + 50],
    ]
    col.insert(batched_entities)


query = '什么是以人为本的座舱'

query_embeddings = ef([query])
