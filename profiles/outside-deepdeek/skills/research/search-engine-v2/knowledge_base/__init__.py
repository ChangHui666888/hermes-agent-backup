"""Knowledge Base V1 — 全球实体关系知识库 (News Knowledge Graph 基础)。

9 本体 YAML (countries/organizations/companies/people/locations/industries/
actions/relations/event_types) + entity_alias.yaml (中英别名归一)。

用法:
  from knowledge_base import loader
  loader.resolve("特朗普")      # → ('PERS_TRUMP', 'Trump', 'Person')
  loader.entity_id("NVIDIA")    # → 'COMP_NVIDIA'
"""
