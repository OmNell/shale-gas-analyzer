"""CrewAI orchestration for shale gas production analysis."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("LITELLM_NUM_RETRIES", "3")

from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task

from shale_gas_analyzer.tools import calculate_decline_metrics_tool, read_shale_data_tool


@CrewBase
class ShaleGasAnalyzerCrew:
    """Hierarchical CrewAI team for shale gas engineering decisions."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self) -> None:
        load_dotenv()
        thinking_max_tokens = int(os.getenv("THINKING_MAX_TOKENS", "8192"))
        regular_max_tokens = int(os.getenv("REGULAR_MAX_TOKENS", "4096"))
        crew_max_rpm = int(os.getenv("CREW_MAX_RPM", "6"))
        self.agent_max_execution_time = int(os.getenv("AGENT_MAX_EXECUTION_TIME", "600"))
        self.crew_max_rpm = crew_max_rpm
        self.thinking_glm_llm = LLM(
            model="openai/glm-4.7",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            temperature=1.0,
            max_tokens=thinking_max_tokens,
            extra_body={"thinking": {"type": "enabled"}},
        )
        self.regular_glm_llm = LLM(
            model="openai/glm-4.7",
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            temperature=0.1,
            max_tokens=regular_max_tokens,
        )

    @agent
    def data_scientist(self) -> Agent:
        return Agent(
            config=self.agents_config["data_scientist"],
            llm=self.regular_glm_llm,
            tools=[read_shale_data_tool, calculate_decline_metrics_tool],
            max_iter=3,
            max_execution_time=self.agent_max_execution_time,
            max_rpm=self.crew_max_rpm,
            verbose=True,
        )

    @agent
    def petroleum_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["petroleum_engineer"],
            llm=self.thinking_glm_llm,
            max_iter=3,
            max_execution_time=self.agent_max_execution_time,
            max_rpm=self.crew_max_rpm,
            verbose=True,
        )

    @agent
    def report_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["report_writer"],
            llm=self.regular_glm_llm,
            max_iter=3,
            max_execution_time=self.agent_max_execution_time,
            max_rpm=self.crew_max_rpm,
            verbose=True,
        )

    def manager_agent(self) -> Agent:
        return Agent(
            role="页岩气生产分析项目经理",
            goal="用最少轮次完成任务分配、审阅和整合，确保团队按数据分析、工程诊断、报告写作顺序产出结论。",
            backstory="你是一名稳健的页岩气开发项目经理，负责层次化调度专家团队。你避免反复讨论，优先让最合适的专家直接完成任务。",
            llm=self.thinking_glm_llm,
            allow_delegation=True,
            max_iter=3,
            max_execution_time=self.agent_max_execution_time,
            max_rpm=self.crew_max_rpm,
            verbose=True,
        )

    @task
    def task_data_analysis(self) -> Task:
        return Task(config=self.tasks_config["task_data_analysis"])

    @task
    def task_engineering_decision(self) -> Task:
        return Task(config=self.tasks_config["task_engineering_decision"])

    @task
    def task_write_final_report(self) -> Task:
        report_path = os.path.join(self._project_root(), "shale_gas_production_report.md")
        return Task(config=self.tasks_config["task_write_final_report"], output_file=report_path)

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.hierarchical,
            manager_agent=self.manager_agent(),
            max_rpm=self.crew_max_rpm,
            output_log_file=os.path.join(self._project_root(), "crew_execution.log"),
            verbose=True,
        )

    def stable_crew(self) -> Crew:
        """Production-safe crew that avoids long manager delegation loops."""
        task_data_analysis = Task(
            config=self.tasks_config["task_data_analysis"],
            agent=self.data_scientist(),
        )
        task_engineering_decision = Task(
            config=self.tasks_config["task_engineering_decision"],
            agent=self.petroleum_engineer(),
            context=[task_data_analysis],
        )
        report_path = os.path.join(self._project_root(), "shale_gas_production_report.md")
        task_write_final_report = Task(
            config=self.tasks_config["task_write_final_report"],
            agent=self.report_writer(),
            context=[task_data_analysis, task_engineering_decision],
            output_file=report_path,
        )
        return Crew(
            agents=[self.data_scientist(), self.petroleum_engineer(), self.report_writer()],
            tasks=[task_data_analysis, task_engineering_decision, task_write_final_report],
            process=Process.sequential,
            max_rpm=self.crew_max_rpm,
            output_log_file=os.path.join(self._project_root(), "crew_execution.log"),
            verbose=True,
        )

    @staticmethod
    def _project_root() -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(os.path.join(current_dir, os.pardir, os.pardir))
