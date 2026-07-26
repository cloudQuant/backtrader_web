# Design Document: Roadmap Epics & Stories 生成

## Overview

本设计文档描述如何将 `docs/STRATEGIC_ROADMAP.md` 战略路线图文档解析并转换为结构化的 Epics 和 Stories 输出文档。整个流程是一个文档到文档的转换管道，由四个核心模块组成：Roadmap_Parser、Epic_Generator、Story_Generator 和 Output_Formatter。

## Architecture

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    文档生成管道 (Pipeline)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐    ┌───────────────┐    ┌────────────────┐    │
│  │ Roadmap_     │    │ Epic_         │    │ Story_         │    │
│  │ Parser       │───→│ Generator     │───→│ Generator      │    │
│  │              │    │               │    │                │    │
│  │ • 读取 MD    │    │ • 生成 Epic   │    │ • 生成 Story   │    │
│  │ • 识别结构   │    │ • 提取元数据  │    │ • 分配属性     │    │
│  │ • 提取数据   │    │ • 里程碑处理  │    │ • 推断缺失值   │    │
│  └──────────────┘    └───────────────┘    └────────────────┘    │
│                                                    │              │
│                                           ┌────────▼────────┐    │
│                                           │ Output_         │    │
│                                           │ Formatter       │    │
│                                           │                 │    │
│                                           │ • 格式化输出    │    │
│                                           │ • 生成摘要表    │    │
│                                           │ • 依赖图汇总    │    │
│                                           │ • 可追溯性映射  │    │
│                                           └─────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 数据流

```
STRATEGIC_ROADMAP.md
        │
        ▼
┌─────────────────┐
│ ParsedRoadmap   │  中间数据结构
│ ├── phases[]    │
│ │   ├── id     │
│ │   ├── title  │
│ │   ├── time   │
│ │   ├── desc   │
│ │   ├── subs[] │
│ │   │   ├── tasks[] │
│ │   │   └── name    │
│ │   └── milestones[] │
│ └── metadata   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ GeneratedDoc    │  最终输出
│ ├── summary     │
│ ├── epics[]     │
│ │   ├── stories[] │
│ │   └── milestones │
│ ├── dep_graph   │
│ └── traceability│
└─────────────────┘
         │
         ▼
  EPICS_AND_STORIES.md
```

## Components and Interfaces

### 1. Roadmap_Parser — 路线图解析器

#### 职责

解析 Markdown 格式的战略路线图文档，提取结构化数据。

#### 解析策略

路线图文档具有固定的层次结构：

```
# 文档标题
## 5. 技术路线图          ← 目标章节
### Phase N: 标题（时间范围）  ← Epic 来源
#### N.M 子模块名称         ← Sub_Module 来源
| 任务 | 优先级 | ... |     ← Story 来源（表格行）
- [ ] 里程碑项             ← Milestone 来源
```

#### 解析规则

| 源结构 | 识别方式 | 提取内容 |
|--------|----------|----------|
| Phase 标题 | `### Phase N:` 正则匹配 | Phase ID、标题、时间范围 |
| Phase 描述 | `>` 引用块 | 目标描述 |
| Sub_Module | `#### N.M` 标题 | 子模块 ID、名称 |
| 任务行 (Phase 1-3) | 表格行 `\| 任务 \| 优先级 \| 预计工期 \| 负责方向/技术方案 \|` | 任务名、优先级、工期、方向 |
| 任务行 (Phase 4) | 表格行 `\| 任务 \| 描述 \| 预期成果 \|` | 任务名、描述、预期成果 |
| 里程碑 | `- [ ]` 列表项 | 里程碑描述 |

#### Phase 4 特殊处理

Phase 4 使用不同的表格列结构：

| Phase 1-3 列 | Phase 4 列 | 映射关系 |
|--------------|------------|----------|
| 优先级 | （缺失） | 默认 P1 |
| 预计工期 | （缺失） | 默认 2-4 周 |
| 负责方向/技术方案 | （缺失） | 从任务内容推断 |
| — | 描述 | → Story 描述 |
| — | 预期成果 | → 验收标准 |

### 2. Epic_Generator — Epic 生成器

#### 职责

将解析出的 Phase 数据转换为结构化的 Epic。

#### Epic 数据模型

```python
@dataclass
class Epic:
    epic_id: str              # "1", "2", "3", "4"
    title: str                # "基础加固", "AI 深度集成", "平台化", "生态建设"
    phase_description: str    # Phase 目标描述
    time_range: str           # "2026 Q2-Q3", "2026 Q3-Q4", etc.
    target_objectives: str    # 从描述中提取的目标
    milestone_checklist: list[str]  # 里程碑列表
    sub_modules: list[SubModule]    # 子模块列表
```

#### 生成规则

1. Phase 编号直接作为 Epic ID 前缀（Phase 1 → Epic 1）
2. Phase 标题作为 Epic 标题
3. `>` 引用块内容作为 Phase 描述和目标
4. 时间范围从 Phase 标题括号中提取
5. `- [ ]` 列表项收集为里程碑（不生成 Story）
6. 子模块标题作为 Epic 内的分组

### 3. Story_Generator — Story 生成器

#### 职责

将每个任务行转换为完整格式的 Story。

#### Story 数据模型

```python
@dataclass
class Story:
    story_id: str             # "1.1.1", "2.3.4" 格式
    title: str                # 任务名称
    user_story: str           # "As a [role], I want [feature], so that [benefit]"
    acceptance_criteria: list[str]  # 至少 2 条，Given/When/Then 格式
    priority: str             # "P0" | "P1" | "P2"
    estimated_duration: str   # "3 天" | "2 周" 格式
    dependencies: list[str]   # Story ID 列表或 ["None"]
    responsible_direction: str  # 从允许集合中选取
    source_location: str      # 可追溯性：源文档位置
```

#### ID 分配规则

```
Story ID = {Epic_ID}.{Sub_Module_Sequence}.{Story_Sequence}

示例：
  Epic 1, Sub_Module 1, Story 3 → "1.1.3"
  Epic 2, Sub_Module 3, Story 4 → "2.3.4"
```

#### 用户故事生成规则

根据任务内容和所属模块推断角色和收益：

| 负责方向 | 默认角色 |
|----------|----------|
| 后端 | 开发者 |
| 前端 | 用户/开发者 |
| 文档 | 用户/贡献者 |
| DevOps | 运维工程师 |
| QA | QA 工程师 |
| 安全 | 安全工程师 |
| 产品 | 产品经理 |
| AI/ML | 数据科学家/用户 |
| 全栈 | 开发者 |

#### 验收标准生成规则

1. 每个 Story 至少 2 条 AC
2. 使用 Given/When/Then 格式
3. 如果源数据包含完成标准（如 Phase 4 的"预期成果"），直接转化为 AC
4. 补充的 AC 应基于任务性质推断（如 API 任务需要文档更新、测试覆盖等）

#### 优先级分配规则

```
IF 源数据有明确优先级:
    使用源数据优先级
ELIF Phase == 4:
    默认 P1
ELSE:
    根据任务在 Sub_Module 中的位置推断:
    - 第一个任务倾向 P0（基础性工作）
    - 中间任务倾向 P1
    - 最后的任务倾向 P2（增强性工作）
```

#### 工期分配规则

```
IF 源数据有明确工期:
    使用源数据工期
ELIF Phase == 4:
    默认 2-4 周（根据任务复杂度在范围内选择）
ELSE:
    根据相似任务推断

格式规则:
    < 7 天 → 使用 "X 天"
    >= 7 天 → 使用 "Y 周"
```

#### 负责方向分配规则

允许的方向标签集合：`{后端, 前端, 全栈, 文档, DevOps, QA, 安全, 产品, AI/ML}`

```
IF 源数据有明确负责方向:
    使用源数据方向
ELIF 源数据有技术方案列:
    从技术方案内容推断:
    - 含 "LLM/AI/ML/模型" → AI/ML
    - 含 "前端/Vue/React/UI" → 前端
    - 含 "API/后端/数据库" → 后端
    - 含 "Docker/K8s/CI" → DevOps
    - 含 "测试/覆盖率" → QA
    - 含 "安全/加密/审计" → 安全
    - 含 "文档/教程" → 文档
    - 其他 → 全栈
ELIF Phase == 4:
    从任务名称推断（同上规则）
```

#### 依赖关系推断规则

```
1. 同一 Sub_Module 内，后续任务可能依赖前置任务（基于语义关联）
2. 跨 Sub_Module 依赖：基础设施任务（如数据库迁移）被功能任务依赖
3. 跨 Epic 依赖：Phase 2+ 的任务可能依赖 Phase 1 的基础工作
4. 无依赖的任务标记为 "None"
5. 所有依赖引用必须使用完整的 Story ID（"X.Y.Z" 格式）
```

### 4. Output_Formatter — 输出格式化器

#### 职责

将生成的 Epics 和 Stories 格式化为最终的 Markdown 文档。

#### 输出文档结构

```markdown
# Backtrader Web — Epics & Stories

## 摘要

| 指标 | 数值 |
|------|------|
| Epic 总数 | 4 |
| Story 总数 | XX |
| Epic 1 Stories | XX |
| Epic 2 Stories | XX |
| Epic 3 Stories | XX |
| Epic 4 Stories | XX |

---

## Epic 1: 基础加固（2026 Q2-Q3）

**目标**: ...
**时间范围**: 2026 Q2-Q3

### 里程碑
- [ ] ...

### 1.1 v2.0.0 正式发布

#### Story 1.1.1: 移除所有废弃 API

**用户故事**: As a 开发者, I want ...

**验收标准**:
1. Given ... When ... Then ...
2. Given ... When ... Then ...

| 属性 | 值 |
|------|------|
| 优先级 | P0 |
| 预估工期 | 2 周 |
| 依赖 | None |
| 负责方向 | 后端 |

---

[... 更多 Stories ...]

---

## 依赖关系图

### 跨 Sub_Module 依赖
| Story | 依赖 | 说明 |
|-------|------|------|
| ... | ... | ... |

### 跨 Epic 依赖
| Story | 依赖 | 说明 |
|-------|------|------|
| ... | ... | ... |

---

## 可追溯性矩阵

| Story ID | 源位置 (Phase.Sub_Module) | 任务名称 |
|----------|--------------------------|----------|
| 1.1.1 | Phase 1 > 1.1 v2.0.0 正式发布 | 移除所有废弃 API |
| ... | ... | ... |
```

#### Story 模板

每个 Story 使用统一模板：

```markdown
#### Story {ID}: {Title}

**用户故事**: As a {role}, I want {feature}, so that {benefit}.

**验收标准**:
1. Given {context}, When {action}, Then {expected_result}
2. Given {context}, When {action}, Then {expected_result}

| 属性 | 值 |
|------|------|
| 优先级 | {P0/P1/P2} |
| 预估工期 | {duration} |
| 依赖 | {dependency_list or "None"} |
| 负责方向 | {direction} |
```

#### 标题层级规则

| 文档元素 | Markdown 标题级别 |
|----------|-------------------|
| 文档标题 | `#` (H1) |
| Epic | `##` (H2) |
| Sub_Module | `###` (H3) |
| Story | `####` (H4) |

### 5. Interfaces

#### 输入接口

| 参数 | 类型 | 描述 |
|------|------|------|
| roadmap_path | str | 路线图文件路径（`docs/STRATEGIC_ROADMAP.md`） |

#### 输出接口

| 参数 | 类型 | 描述 |
|------|------|------|
| output_path | str | 输出文件路径 |
| format | str | 输出格式（固定为 Markdown） |

#### 模块间接口

```python
# Parser → Generator
@dataclass
class ParsedPhase:
    phase_id: int
    title: str
    time_range: str
    description: str
    sub_modules: list[ParsedSubModule]
    milestones: list[str]

@dataclass
class ParsedSubModule:
    sequence: int
    name: str
    tasks: list[ParsedTask]

@dataclass
class ParsedTask:
    name: str
    priority: str | None       # None if not specified
    duration: str | None       # None if not specified
    direction: str | None      # "负责方向" column
    tech_approach: str | None  # "技术方案" column (Phase 2-3)
    description: str | None    # "描述" column (Phase 4)
    expected_outcome: str | None  # "预期成果" column (Phase 4)
```

## Data Models

### 核心数据模型关系

```
ParsedRoadmap (1) ──── (4) ParsedPhase
ParsedPhase   (1) ──── (4) ParsedSubModule
ParsedSubModule (1) ── (N) ParsedTask

Epic          (1) ──── (1) ParsedPhase
Epic          (1) ──── (N) SubModuleGroup
SubModuleGroup (1) ── (N) Story
Story         (1) ──── (N) AcceptanceCriteria
Story         (1) ──── (N) Dependency
```

### 约束条件

| 约束 | 描述 |
|------|------|
| Epic 数量 | 恒为 4 |
| Sub_Module 数量 | 每个 Epic 恒为 4 |
| Story 总数 | 60-80 范围 |
| Story ID 唯一性 | 全局唯一 |
| 依赖引用有效性 | 所有引用的 Story ID 必须存在 |
| 优先级值域 | {P0, P1, P2} |
| 方向值域 | {后端, 前端, 全栈, 文档, DevOps, QA, 安全, 产品, AI/ML} |

## Error Handling

### 解析错误

| 错误场景 | 处理策略 |
|----------|----------|
| 路线图文件不存在 | 终止并报错 |
| Phase 结构不完整 | 跳过该 Phase 并警告 |
| 表格格式异常 | 尝试宽松解析，失败则跳过该行并警告 |
| 表格列数不匹配 | 根据列数自动识别 Phase 1-3 或 Phase 4 格式 |

### 生成错误

| 错误场景 | 处理策略 |
|----------|----------|
| 无法推断优先级 | 使用 P1 作为默认值 |
| 无法推断工期 | 使用 "2 周" 作为默认值 |
| 无法推断负责方向 | 使用 "全栈" 作为默认值 |
| 依赖引用无效 | 移除无效引用并警告 |
| Story 总数超出 60-80 范围 | 记录警告但继续生成 |

### 验证检查

生成完成后执行以下验证：

1. Epic 数量 == 4
2. 每个 Epic 包含 4 个 Sub_Module
3. 所有 Story ID 唯一
4. 所有依赖引用指向有效 Story ID
5. 所有优先级值在允许集合内
6. 所有负责方向值在允许集合内
7. 所有 Story 至少有 2 条 AC
8. Story 总数在 60-80 范围内

## Testing Strategy

### 单元测试

- **Parser 测试**: 使用路线图文档片段验证解析逻辑（Phase 识别、表格解析、里程碑提取）
- **Generator 测试**: 验证 Epic/Story 生成的字段完整性、ID 格式、默认值分配
- **Formatter 测试**: 验证输出 Markdown 的标题层级、模板一致性

### 属性测试

- 使用 Hypothesis 生成随机的路线图结构数据，验证以下不变量：
  - Story ID 全局唯一性
  - 依赖引用有效性
  - 字段值域约束
  - 1:1 映射完整性

### 集成测试

- 使用完整的 `docs/STRATEGIC_ROADMAP.md` 作为输入，验证端到端生成结果
- 验证 Story 总数在 60-80 范围内
- 验证输出文档可被 Markdown 解析器正确解析

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Epic 数量不变性

*For any* valid strategic roadmap document containing 4 Phases, the Epic_Generator SHALL produce exactly 4 Epics, each corresponding to one Phase in order.

**Validates: Requirements 1.1**

### Property 2: Epic 结构完整性

*For any* generated Epic, it SHALL contain all required fields (Epic ID, title, phase description, time range, target objectives, milestone checklist, sub_module group headings), and the Epic ID prefix SHALL match the source Phase number, and the time range SHALL match the source Phase time range.

**Validates: Requirements 1.2, 1.3, 1.4, 1.5**

### Property 3: 层次化 ID 格式与唯一性

*For any* Sub_Module, its ID SHALL follow the format "X.Y" (where X is Epic ID, Y is sequence number). *For any* Story, its ID SHALL follow the format "X.Y.Z" (where X.Y is Sub_Module ID, Z is sequence number). *For any* two Stories in the output, their IDs SHALL be distinct.

**Validates: Requirements 2.6, 3.3**

### Property 4: 任务到 Story 的双射映射

*For any* task row in the source roadmap, there SHALL exist exactly one corresponding Story in the output. *For any* Story in the output, there SHALL exist exactly one corresponding task row in the source. The total Story count SHALL equal the total task row count.

**Validates: Requirements 3.1, 10.1, 10.2**

### Property 5: 源数据保真性

*For any* Story whose source task row specifies an explicit value for task name, priority, duration, or responsible direction, the corresponding Story field SHALL preserve that exact value unchanged.

**Validates: Requirements 3.4, 5.2, 6.2, 8.2**

### Property 6: Story 结构完整性与模板一致性

*For any* generated Story, it SHALL contain all required fields (title, user story, acceptance criteria, priority, estimated duration, dependencies, responsible direction). The user story SHALL follow "As a [role], I want [feature], so that [benefit]" format. The acceptance criteria SHALL contain at least 2 items, each in Given/When/Then or equivalent verifiable format.

**Validates: Requirements 3.5, 4.1, 4.3, 7.1, 8.1, 9.4**

### Property 7: 字段值域约束

*For any* generated Story: the priority SHALL be one of {P0, P1, P2}; the estimated duration SHALL be expressed in days (for < 7 days) or weeks (for >= 7 days); the responsible direction SHALL be one of {后端, 前端, 全栈, 文档, DevOps, QA, 安全, 产品, AI/ML}.

**Validates: Requirements 5.1, 6.1, 6.4, 8.4**

### Property 8: 依赖引用完整性

*For any* Story with dependencies, each referenced Story ID SHALL exist in the output document. *For any* Story without dependencies, the dependency field SHALL be "None". *For any* cross-Epic dependency, the full hierarchical ID format "X.Y.Z" SHALL be used.

**Validates: Requirements 7.2, 7.3, 7.4, 7.5**

### Property 9: Story 按 Sub_Module 分组

*For any* Story, it SHALL be placed under the correct Sub_Module group heading that corresponds to its source task row's Sub_Module in the roadmap.

**Validates: Requirements 2.1**

### Property 10: 输出标题层级一致性

*For any* element in the output document: Epics SHALL use level-2 headings (##), Sub_Modules SHALL use level-3 headings (###), and Stories SHALL use level-4 headings (####).

**Validates: Requirements 9.2**

### Property 11: 可追溯性完整性

*For any* Story in the output, there SHALL exist a corresponding entry in the traceability matrix that maps the Story ID back to its source Phase and Sub_Module location in the roadmap document.

**Validates: Requirements 10.3**

### Property 12: 里程碑分类正确性

*For any* milestone item (checkbox item) in the source roadmap, it SHALL appear in the corresponding Epic's milestone checklist AND SHALL NOT be generated as a separate Story.

**Validates: Requirements 10.4**

### Property 13: Phase 4 格式适配

*For any* Phase 4 task row: the "描述" column SHALL map to Story description, the "预期成果" column SHALL map to acceptance criteria. If no explicit priority exists, priority SHALL default to P1. If no explicit duration exists, duration SHALL be in the 2-4 weeks range.

**Validates: Requirements 11.1, 11.2, 11.3, 11.4**
