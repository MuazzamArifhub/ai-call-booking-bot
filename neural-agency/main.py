"""
NeuralAgency - AI-Native Full-Service Marketing Agency
Built for Y Combinator Spring 2026 (AI-Native Agencies category)

Instead of selling a $50/mo SaaS tool, we use AI to do the agency work
and deliver finished campaign deliverables worth $5,000+.
"""

import os
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional

import anthropic
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from database import init_db, create_job, get_job, get_all_jobs, update_job_status, save_job_results, save_job_error
from agents import run_strategy_agent, run_copy_agent, run_content_agent, run_seo_agent

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="NeuralAgency",
    description="AI-Native Full-Service Marketing Agency - YC Spring 2026",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class ClientBrief(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=100)
    product_description: str = Field(..., min_length=20, max_length=1000)
    target_audience: str = Field(..., min_length=10, max_length=500)
    campaign_goal: str = Field(..., min_length=10, max_length=300)
    brand_voice: Optional[str] = Field(default="Professional but approachable", max_length=200)
    budget_range: Optional[str] = Field(default="Not specified", max_length=100)
    timeline: Optional[str] = Field(default="30 days", max_length=100)
    differentiators: Optional[str] = Field(default="Not specified", max_length=500)
    deliverables: list[str] = Field(
        default=["strategy", "copy", "social_content", "seo"],
        description="Which deliverables to generate"
    )


async def run_agency_pipeline(job_id: str, brief: dict):
    """
    Orchestrates all AI agents in parallel where possible.
    Strategy runs first, then copy/content/seo run in parallel using the strategy output.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        await save_job_error(job_id, "ANTHROPIC_API_KEY not configured")
        return

    client = anthropic.AsyncAnthropic(api_key=api_key)
    deliverables = brief.get("deliverables", ["strategy", "copy", "social_content", "seo"])

    try:
        await update_job_status(job_id, "running_strategy")

        # Phase 1: Strategy (foundation for all other agents)
        strategy = await run_strategy_agent(client, brief)

        await update_job_status(job_id, "running_deliverables")

        # Phase 2: Run remaining agents in parallel
        tasks = {}

        if "copy" in deliverables:
            tasks["copy_assets"] = run_copy_agent(client, brief, strategy)

        if "social_content" in deliverables:
            tasks["social_content"] = run_content_agent(client, brief, strategy)

        if "seo" in deliverables:
            tasks["seo_content"] = run_seo_agent(client, brief, strategy)

        results = {"strategy": strategy}

        if tasks:
            gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for key, result in zip(tasks.keys(), gathered):
                if isinstance(result, Exception):
                    results[key] = f"Error generating {key}: {str(result)}"
                else:
                    results[key] = result

        await save_job_results(job_id, results)

    except Exception as e:
        await save_job_error(job_id, str(e))


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    jobs = await get_all_jobs()
    for job in jobs:
        if isinstance(job.get("brief"), str):
            try:
                job["brief"] = json.loads(job["brief"])
            except Exception:
                pass
    return templates.TemplateResponse("dashboard.html", {"request": request, "jobs": jobs})


@app.get("/results/{job_id}", response_class=HTMLResponse)
async def results_page(request: Request, job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if isinstance(job.get("brief"), str):
        try:
            job["brief"] = json.loads(job["brief"])
        except Exception:
            pass
    return templates.TemplateResponse("results.html", {"request": request, "job": job})


@app.post("/api/brief", status_code=202)
async def submit_brief(brief: ClientBrief, background_tasks: BackgroundTasks):
    """Submit a client brief and start the agency pipeline."""
    brief_dict = brief.model_dump()
    job_id = await create_job(brief_dict)
    background_tasks.add_task(run_agency_pipeline, job_id, brief_dict)
    return {"job_id": job_id, "status": "pending", "message": "Your brief is being processed by our AI agents."}


@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    """Poll job status and results."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job_id,
        "status": job["status"],
        "created_at": job["created_at"],
        "completed_at": job.get("completed_at"),
    }

    if job["status"] == "completed":
        response["results"] = {
            "strategy": job.get("strategy"),
            "copy_assets": job.get("copy_assets"),
            "social_content": job.get("social_content"),
            "seo_content": job.get("seo_content"),
        }

    if job["status"] == "failed":
        response["error"] = job.get("error")

    return response


@app.get("/api/jobs")
async def list_jobs():
    """List recent jobs."""
    jobs = await get_all_jobs()
    return {"jobs": jobs}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "NeuralAgency", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
