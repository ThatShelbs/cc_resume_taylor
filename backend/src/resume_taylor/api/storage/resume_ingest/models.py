"""The resume structure shared by every ingestion step."""

from pydantic import BaseModel


class Education(BaseModel):
    institution: str = ""
    location: str = ""
    dates: str = ""
    degree: str = ""


class Job(BaseModel):
    company: str = ""
    location: str = ""
    dates: str = ""
    title: str = ""
    bullets: list[str] = []


class OtherSection(BaseModel):
    title: str
    lines: list[str] = []


class Flag(BaseModel):
    path: str  # e.g. "jobs.0.bullets.2"
    message: str


class ResumeStructure(BaseModel):
    summary: str = ""
    education: list[Education] = []
    jobs: list[Job] = []
    other_sections: list[OtherSection] = []
    flags: list[Flag] = []
    source: str = ""  # "docx" | "heuristic" | "ai" | "current"
    source_file: str = ""
    raw_text: str = ""
    contact_lines: list[str] = []


class IngestError(ValueError):
    pass
