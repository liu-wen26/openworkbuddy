# AI自动阅卷系统 — 数据库设计

> 版本：V1.0  
> 数据库：PostgreSQL 15  
> ORM：SQLAlchemy 2.0

## 1. 用户与权限

### users（用户表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 用户ID |
| username | VARCHAR(64) UNIQUE | 登录账号 |
| real_name | VARCHAR(64) | 真实姓名 |
| password_hash | VARCHAR(255) | 密码哈希 |
| role | VARCHAR(32) | 角色：super_admin / exam_admin / group_leader / teacher |
| email | VARCHAR(128) | 邮箱 |
| phone | VARCHAR(32) | 电话 |
| is_active | BOOLEAN | 是否启用 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

### role_permissions（角色权限表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| role | VARCHAR(32) | 角色标识 |
| permission_code | VARCHAR(128) | 权限码，如 `exam:create`, `paper:upload` |
| description | VARCHAR(255) | 描述 |

## 2. 考试管理

### exams（考试表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 考试ID |
| name | VARCHAR(255) | 考试名称 |
| subject | VARCHAR(64) | 学科 |
| grade | VARCHAR(64) | 年级 |
| exam_type | VARCHAR(64) | 考试类型：weekly/monthly/midterm/final/mock |
| total_score | DECIMAL(8,2) | 总分 |
| pass_score | DECIMAL(8,2) | 及格线 |
| excellent_score | DECIMAL(8,2) | 优秀线 |
| answer_card_template_id | UUID FK | 绑定的答题卡模板 |
| original_paper_path | VARCHAR(512) | 原试卷PDF存储路径（可选） |
| original_paper_uploaded_by | UUID FK | 上传人 |
| original_paper_uploaded_at | TIMESTAMPTZ | 上传时间 |
| status | VARCHAR(32) | 状态：draft / ready / importing / grading / locked / archived |
| grading_start_at | TIMESTAMPTZ | 阅卷开始时间 |
| grading_end_at | TIMESTAMPTZ | 阅卷结束时间 |
| created_by | UUID FK | 创建人 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

### exam_teachers（考试-阅卷教师关联表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | 考试ID |
| teacher_id | UUID FK | 教师ID |
| role_in_exam | VARCHAR(32) | 本场角色：grader / leader |
| assigned_at | TIMESTAMPTZ | 分配时间 |

### students（考生表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 考生ID |
| exam_number | VARCHAR(64) | 考号 |
| name | VARCHAR(64) | 姓名 |
| class_name | VARCHAR(64) | 班级 |
| created_at | TIMESTAMPTZ | |

### exam_students（考试-考生关联表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | |
| student_id | UUID FK | |
| is_absent | BOOLEAN | 是否缺考（扫描未出现该考号） |
| total_score | DECIMAL(8,2) | 最终总分 |
| rank_in_grade | INTEGER | 年级排名 |
| rank_in_class | INTEGER | 班级排名 |

## 3. 答题卡模板

### answer_card_templates（答题卡模板表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 模板ID |
| name | VARCHAR(255) | 模板名称 |
| paper_size | VARCHAR(16) | A3 / A4 |
| duplex | BOOLEAN | 是否双面 |
| margin_top | DECIMAL(6,2) | 上边距 mm |
| margin_bottom | DECIMAL(6,2) | 下边距 mm |
| margin_left | DECIMAL(6,2) | 左边距 mm |
| margin_right | DECIMAL(6,2) | 右边距 mm |
| title | VARCHAR(255) | 答题卡标题 |
| source_pdf_path | VARCHAR(512) | 导入的原始PDF路径（可选） |
| is_blank | BOOLEAN | 是否是空白答题卡 |
| created_by | UUID FK | |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### template_regions（模板识别区域表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| template_id | UUID FK | 所属模板 |
| page_index | INTEGER | 页码（0-based） |
| region_type | VARCHAR(32) | 类型：exam_number / name / choice / subjective |
| question_number | VARCHAR(64) | 题号，如 1、26-1 |
| sub_question_number | VARCHAR(64) | 子题号 |
| max_score | DECIMAL(8,2) | 满分 |
| x | DECIMAL(8,2) | 左上角x坐标（像素或百分比） |
| y | DECIMAL(8,2) | 左上角y坐标 |
| width | DECIMAL(8,2) | 宽度 |
| height | DECIMAL(8,2) | 高度 |
| options_count | INTEGER | 选择题选项数量（A-D=4, A-E=5） |
| allow_multiple | BOOLEAN | 是否不定项多选 |
| partial_score_rules | JSONB | 多选部分得分规则 |
| config | JSONB | 扩展配置 |
| created_at | TIMESTAMPTZ | |

### choice_answers（选择题标准答案表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | 每场考试独立答案 |
| template_id | UUID FK | |
| question_number | VARCHAR(64) | 题号 |
| correct_options | VARCHAR(32) | 正确答案，如 "AB" |
| score | DECIMAL(6,2) | 满分 |
| partial_score_rules | JSONB | 部分得分规则 |

### ai_scoring_configs（AI评分配置表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | 每场考试独立配置 |
| question_number | VARCHAR(64) | 题号 |
| standard_answer | TEXT | 参考答案 |
| scoring_points | JSONB | 采分要点列表 |
| deduction_notes | TEXT | 扣分说明 |
| prompt_template | TEXT | 自定义Prompt |
| confidence_threshold | DECIMAL(4,3) | AI置信度阈值 |
| score_tolerance | DECIMAL(6,2) | AI打分误差阈值 |
| enabled | BOOLEAN | 是否启用AI预评 |

## 4. 答卷导入与题块

### import_batches（导入批次表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | |
| import_type | VARCHAR(32) | pdf / image |
| status | VARCHAR(32) | pending / processing / completed / failed |
| total_files | INTEGER | 上传文件数 |
| total_pages | INTEGER | 总页数/总图片数 |
| processed_pages | INTEGER | 已处理页数 |
| source | VARCHAR(32) | formal / precheck |
| created_by | UUID FK | |
| created_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |

### imported_pages（导入的答卷页表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| batch_id | UUID FK | |
| exam_id | UUID FK | |
| source_type | VARCHAR(32) | pdf / image |
| original_file_path | VARCHAR(512) | 原始文件路径 |
| original_page_index | INTEGER | 在PDF中的页码 |
| preprocessed_image_path | VARCHAR(512) | 预处理后图像路径 |
| student_id | UUID FK | 匹配到的考生 |
| exam_number_ocr | VARCHAR(64) | 识别出的考号 |
| status | VARCHAR(32) | pending / matched / exception / processed |
| created_at | TIMESTAMPTZ | |

### answer_blocks（题块表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| page_id | UUID FK | 所属答卷页 |
| exam_id | UUID FK | |
| student_id | UUID FK | |
| region_id | UUID FK | 对应模板区域 |
| question_number | VARCHAR(64) | 题号 |
| block_type | VARCHAR(32) | choice / subjective |
| image_path | VARCHAR(512) | 切割后题块图片路径 |
| x | DECIMAL(8,2) | 切割坐标 |
| y | DECIMAL(8,2) | |
| width | DECIMAL(8,2) | |
| height | DECIMAL(8,2) | |
| status | VARCHAR(32) | pending / scored / exception / arbitrated |

## 5. 选择题判分

### omr_results（OMR识别结果表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| block_id | UUID FK | |
| exam_id | UUID FK | |
| student_id | UUID FK | |
| question_number | VARCHAR(64) | |
| detected_options | VARCHAR(32) | 识别到的选项 |
| is_exception | BOOLEAN | 是否异常 |
| exception_type | VARCHAR(64) | 异常类型：multi / blank / fuzzy |
| auto_score | DECIMAL(6,2) | 自动判分分数 |
| final_score | DECIMAL(6,2) | 最终分数 |
| reviewed_by | UUID FK | 复核人 |
| reviewed_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |

## 6. 非选择题评分

### scoring_tasks（阅卷任务表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | |
| block_id | UUID FK | |
| teacher_id | UUID FK | 分配教师 |
| round | INTEGER | 阅卷轮次（1=一评，2=二评） |
| mode | VARCHAR(32) | manual / ai_pre / double |
| status | VARCHAR(32) | pending / completed / arbitrated |
| score | DECIMAL(6,2) | 该轮分数 |
| comment | TEXT | 评语 |
| created_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | |

### ai_scores（AI预评分表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| block_id | UUID FK | |
| exam_id | UUID FK | |
| score | DECIMAL(6,2) | AI预估分数 |
| confidence | DECIMAL(4,3) | 置信度 |
| comment | TEXT | AI评语 |
| reasoning | TEXT | 推理过程 |
| is_low_confidence | BOOLEAN | 是否低置信 |
| ocr_text | TEXT | OCR识别手写文本 |
| model_name | VARCHAR(128) | 使用的模型 |
| created_at | TIMESTAMPTZ | |

### subjective_scores（非选择题最终得分表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| block_id | UUID FK | |
| exam_id | UUID FK | |
| student_id | UUID FK | |
| question_number | VARCHAR(64) | |
| score | DECIMAL(6,2) | 最终得分 |
| final_teacher_id | UUID FK | 最终确认教师 |
| arbitration_id | UUID FK | 仲裁记录 |
| comment | TEXT | 评语 |
| tags | JSONB | 标记：typical_error / excellent / blank |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### arbitrations（仲裁记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| block_id | UUID FK | |
| exam_id | UUID FK | |
| teacher1_id | UUID FK | 一评教师 |
| teacher1_score | DECIMAL(6,2) | 一评分数 |
| teacher2_id | UUID FK | 二评教师 |
| teacher2_score | DECIMAL(6,2) | 二评分数 |
| arbitrator_id | UUID FK | 仲裁教师 |
| final_score | DECIMAL(6,2) | 仲裁最终分 |
| reason | TEXT | 仲裁理由 |
| created_at | TIMESTAMPTZ | |

### scoring_logs（阅卷痕迹日志表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| score_id | UUID FK | |
| operation | VARCHAR(64) | 操作：create / update |
| old_score | DECIMAL(6,2) | 修改前分数 |
| new_score | DECIMAL(6,2) | 修改后分数 |
| operator_id | UUID FK | |
| operated_at | TIMESTAMPTZ | |
| ip_address | VARCHAR(64) | |

## 7. 异常中心

### exceptions（异常表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | |
| page_id | UUID FK | 相关答卷页 |
| block_id | UUID FK | 相关题块 |
| exception_type | VARCHAR(64) | 异常类型 |
| source | VARCHAR(32) | pdf / image |
| status | VARCHAR(32) | pending / resolved / ignored |
| description | TEXT | 异常描述 |
| snapshot_path | VARCHAR(512) | 异常截图 |
| resolved_by | UUID FK | 处理人 |
| resolved_at | TIMESTAMPTZ | |
| resolution_action | VARCHAR(64) | 处理方式 |
| resolution_note | TEXT | 处理备注 |
| created_at | TIMESTAMPTZ | |

异常类型枚举：
- `exam_number_not_found`：考号识别失败
- `exam_number_not_match`：考号不在花名册
- `tilt_exceed`：倾斜角度超限
- `perspective_exceed`：透视矫正超限
- `cut_failed`：题块切割失败
- `choice_multi`：选择题多涂
- `choice_blank`：选择题漏涂
- `choice_fuzzy`：选择题填涂模糊
- `ai_low_confidence`：AI低置信度
- `manual_review`：人工标记复核

## 8. 预阅卷

### precheck_sessions（预阅卷会话表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | |
| status | VARCHAR(32) | active / cleared |
| sample_count | INTEGER | 样卷数量 |
| created_by | UUID FK | |
| created_at | TIMESTAMPTZ | |
| cleared_at | TIMESTAMPTZ | |

### precheck_pages（预阅卷样卷页表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| session_id | UUID FK | |
| original_file_path | VARCHAR(512) | 原始文件 |
| preprocessed_image_path | VARCHAR(512) | 预处理后 |
| cut_result | JSONB | 切割结果快照 |
| omr_result | JSONB | 选择题识别快照 |
| ai_result | JSONB | AI评分快照 |
| created_at | TIMESTAMPTZ | |

## 9. 学情分析

### question_analytics（题目分析表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | |
| question_number | VARCHAR(64) | 题号 |
| question_type | VARCHAR(32) | choice / subjective |
| max_score | DECIMAL(6,2) | 满分 |
| avg_score | DECIMAL(6,2) | 平均分 |
| score_rate | DECIMAL(5,4) | 得分率 |
| difficulty | DECIMAL(5,4) | 难度系数 |
| discrimination | DECIMAL(5,4) | 区分度 |
| option_distribution | JSONB | 选择题选项分布 |
| knowledge_tags | JSONB | 知识点标签 |
| typical_errors | JSONB | 高频错误汇总 |
| updated_at | TIMESTAMPTZ | |

### class_analytics（班级学情分析表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | |
| class_name | VARCHAR(64) | 班级 |
| student_count | INTEGER | 人数 |
| avg_score | DECIMAL(8,2) | 平均分 |
| max_score | DECIMAL(8,2) | 最高分 |
| min_score | DECIMAL(8,2) | 最低分 |
| pass_rate | DECIMAL(5,4) | 及格率 |
| excellent_rate | DECIMAL(5,4) | 优秀率 |
| score_distribution | JSONB | 分数段分布 |
| question_score_rates | JSONB | 各题得分率 |
| updated_at | TIMESTAMPTZ | |

### student_reports（学生个人学情报告表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| exam_id | UUID FK | |
| student_id | UUID FK | |
| total_score | DECIMAL(8,2) | 总分 |
| rank_in_grade | INTEGER | 年级排名 |
| rank_in_class | INTEGER | 班级排名 |
| question_scores | JSONB | 每小题得分明细 |
| wrong_questions | JSONB | 错题列表 |
| weak_knowledge_points | JSONB | 薄弱知识点 |
| ai_comment | TEXT | AI评语 |
| generated_at | TIMESTAMPTZ | |

## 10. 系统与审计

### system_settings（系统设置表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| key | VARCHAR(128) UNIQUE | 配置键 |
| value | JSONB | 配置值 |
| description | TEXT | 描述 |
| updated_by | UUID FK | |
| updated_at | TIMESTAMPTZ | |

关键配置项：
- `llm.provider`：openai / local
- `llm.api_base`：API地址
- `llm.api_key`：密钥
- `llm.default_model`：默认模型
- `llm.confidence_threshold`：默认置信度阈值
- `watermark.enabled`：水印开关
- `watermark.text`：水印文字
- `watermark.on_original_paper`：原试卷是否加水印

### audit_logs（审计日志表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | |
| user_id | UUID FK | |
| action | VARCHAR(64) | 操作类型 |
| target_type | VARCHAR(64) | 对象类型 |
| target_id | UUID | 对象ID |
| detail | JSONB | 详细内容 |
| ip_address | VARCHAR(64) | |
| created_at | TIMESTAMPTZ | |

操作类型枚举：
- `exam:create`, `exam:update`, `exam:lock`, `exam:unlock`
- `original_paper:upload`, `original_paper:replace`, `original_paper:delete`
- `template:create`, `template:update`
- `import:start`, `import:complete`
- `exception:resolve`, `exception:ignore`
- `score:update`, `score:arbitrate`
- `precheck:start`, `precheck:clear`
- `export:download`, `archive:create`

## 11. 索引建议

```sql
CREATE INDEX idx_exams_status ON exams(status);
CREATE INDEX idx_exam_students_exam_id ON exam_students(exam_id);
CREATE INDEX idx_exam_students_student_id ON exam_students(student_id);
CREATE INDEX idx_imported_pages_exam_id ON imported_pages(exam_id);
CREATE INDEX idx_imported_pages_batch_id ON imported_pages(batch_id);
CREATE INDEX idx_answer_blocks_exam_id ON answer_blocks(exam_id);
CREATE INDEX idx_answer_blocks_student_id ON answer_blocks(student_id);
CREATE INDEX idx_exceptions_exam_id_status ON exceptions(exam_id, status);
CREATE INDEX idx_scoring_tasks_teacher_id ON scoring_tasks(teacher_id);
CREATE INDEX idx_scoring_tasks_exam_id ON scoring_tasks(exam_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);
```
