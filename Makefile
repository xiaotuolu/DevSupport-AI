.PHONY: infra-up infra-down infra-status init-db seed ingest setup run front health clean

# ---------- 基础设施（MySQL / Redis / Milvus）----------
infra-up:        ## 启动基础设施
	docker compose up -d

infra-down:      ## 停止基础设施
	docker compose down

infra-status:    ## 查看基础设施状态
	docker compose ps

# ---------- 数据准备（在 backend 下执行）----------
init-db:         ## 建 MySQL 表 + Milvus collection（--recreate 删表重建）
	cd backend && python -m scripts.init_db --recreate

seed:            ## 灌种子数据（租户/账号/日志/账单）
	cd backend && python -m scripts.seed_data

ingest:          ## 知识库切片向量化入库
	cd backend && python -m scripts.ingest_knowledge

setup: init-db seed ingest   ## 一键准备数据（建表 + 种子 + 知识库）

# ---------- 运行 ----------
run:             ## 启动后端 :8000
	cd backend && uvicorn app.main:app --reload --port 8000

front:           ## 启动前端 :5173
	cd frontend && npm run dev

health:          ## 健康检查
	curl -s http://localhost:8000/api/health

# ---------- 评估 / 压测 ----------
eval:            ## 跑标准评估集（意图/引用/脱敏等指标）
	cd backend && python -m eval.run_eval

bench:           ## 并发压测 + 阶段耗时分解 + 缓存优化对比
	cd backend && python -m benchmark.loadtest

# ---------- 清理 ----------
clean:           ## 停止并清理容器与数据卷
	docker compose down -v
