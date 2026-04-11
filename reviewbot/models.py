from typing import List, Literal, Optional
from pydantic import BaseModel, Field

Severity = Literal["blocker", "major", "minor", "nit"]
Category = Literal["bug", "security", "perf", "style", "design", "docs"]
Verdict = Literal["approve", "approve_with_comments", "request_changes"]


class ReviewComment(BaseModel):
    file: str = Field(..., description="Path of the file this comment applies to")
    line: Optional[int] = Field(
        None, description="Line number inside the diff hunk, or null if file-level"
    )
    severity: Severity
    category: Category
    message: str = Field(..., description="One or two sentence explanation of the issue")
    suggestion: Optional[str] = Field(
        None, description="Concrete fix, if obvious. Null otherwise."
    )


class FileReview(BaseModel):
    file: str
    comments: List[ReviewComment] = Field(default_factory=list)
    summary: str = Field(..., description="One-line summary of this file's review")


class ReviewResult(BaseModel):
    files: List[FileReview] = Field(default_factory=list)
    overall_verdict: Verdict = "approve"
    overall_summary: str = ""
