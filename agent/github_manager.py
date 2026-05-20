"""
github_manager.py — Gestion des dépôts, branches, commits, PR et workflows GitHub.
"""

import base64
import time
from typing import Any, Dict, List, Optional

import requests

from agent.infra_bootstrap import TF_ROOT, get_bootstrap_files


class GitHubManager:
    def __init__(self, config: Any):
        self.token = config.github_token
        self.owner = config.github_owner
        self.repo = config.github_infra_repo
        self.api_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.branch: Optional[str] = None

    def ensure_repo_exists(self) -> str:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code == 404:
            payload = {
                "name": self.repo,
                "description": "Infrastructure as Code - Agent IA DevOps (infra-provisioned)",
                "private": False,
                "auto_init": True,
            }
            resp = requests.post(f"{self.api_url}/user/repos", headers=self.headers, json=payload)
            resp.raise_for_status()
        else:
            resp.raise_for_status()

        data = resp.json()
        return data.get("html_url", f"https://github.com/{self.owner}/{self.repo}")

    def setup_infra_repo(self) -> None:
        """Pipeline CI + bootstrap Terraform dans infra-provisioned."""
        self.ensure_standard_pipeline()
        self.bootstrap_infra_repo()

    def _get_default_branch(self) -> str:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json().get("default_branch", "main")

    def _get_branch_sha(self, branch: str) -> str:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/git/ref/heads/{branch}"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json()["object"]["sha"]

    def create_branch(self, branch: str) -> None:
        default_branch = self._get_default_branch()
        sha = self._get_branch_sha(default_branch)
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/git/refs"
        payload = {"ref": f"refs/heads/{branch}", "sha": sha}
        resp = requests.post(url, headers=self.headers, json=payload)
        if resp.status_code == 201:
            self.branch = branch
            return
        if resp.status_code == 422 and "Reference already exists" in resp.text:
            self.branch = branch
            return
        resp.raise_for_status()

    def _create_or_update_file(
        self, path: str, content: str, branch: str, commit_message: str
    ) -> Dict[str, Any]:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/contents/{path}"
        get_resp = requests.get(url, headers=self.headers, params={"ref": branch})
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if get_resp.status_code == 200:
            payload["sha"] = get_resp.json()["sha"]
        elif get_resp.status_code not in (404, 403):
            get_resp.raise_for_status()

        resp = requests.put(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _normalize_tf_path(filename: str) -> str:
        """Place les .tf sous terraform/ sauf workflows et README racine."""
        if filename.startswith(".github/"):
            return filename
        if filename == "README.md":
            return filename
        if filename.startswith(f"{TF_ROOT}/"):
            return filename
        if filename.endswith(".tf") or filename.endswith(".tfvars") or filename.endswith(".tfvars.example"):
            return f"{TF_ROOT}/{filename}"
        return filename

    def push_files(self, branch: str, files: Dict[str, str], commit_message: str) -> None:
        skip = {"providers.tf", "backend.tf", "variables.tf", "main.tf", "outputs.tf"}
        for filename, content in files.items():
            path = self._normalize_tf_path(filename)
            base = path.split("/")[-1]
            if base in skip and path.startswith(f"{TF_ROOT}/"):
                continue
            self._create_or_update_file(path, content, branch, commit_message)

    def create_pull_request(self, branch: str, analysis: Any, pr_body: str) -> Dict[str, Any]:
        title = f"feat: provision {analysis.project_name} — {analysis.environment}"
        base_branch = self._get_default_branch()
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/pulls"
        payload = {
            "title": title,
            "head": branch,
            "base": base_branch,
            "body": pr_body,
        }
        resp = requests.post(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        self.branch = branch
        return resp.json()

    def _get_pr(self, pr_number: int) -> Dict[str, Any]:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/pulls/{pr_number}"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def _list_workflow_runs(
        self, branch: Optional[str] = None, event: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/actions/runs"
        params: Dict[str, Any] = {"per_page": 30}
        if branch:
            params["branch"] = branch
        if event:
            params["event"] = event
        resp = requests.get(url, headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json().get("workflow_runs", [])

    def wait_for_plan_completion(self, pr_number: int, timeout_minutes: int = 15) -> Optional[Dict[str, Any]]:
        pr = self._get_pr(pr_number)
        branch = pr["head"]["ref"]
        deadline = time.time() + timeout_minutes * 60
        while time.time() < deadline:
            runs = self._list_workflow_runs(branch=branch, event="pull_request")
            for run in runs:
                if run.get("head_branch") == branch and run.get("status") == "completed":
                    return run
            time.sleep(10)
        return None

    def wait_for_apply_completion(
        self, branch: str = "main", timeout_minutes: int = 25
    ) -> Optional[Dict[str, Any]]:
        deadline = time.time() + timeout_minutes * 60
        while time.time() < deadline:
            runs = self._list_workflow_runs(branch=branch, event="push")
            for run in runs:
                name = run.get("name", "")
                if "Apply" in name or "infra-provisioned" in name:
                    if run.get("status") == "completed":
                        return run
            time.sleep(15)
        return None

    def get_plan_output(self, run_id: int) -> str:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/jobs"
        resp = requests.get(url, headers=self.headers, params={"per_page": 50})
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
        lines = []
        for job in jobs:
            lines.append(
                f"Job {job['name']}: {job.get('conclusion', 'unknown')} ({job.get('status', 'unknown')})"
            )
            for step in job.get("steps", []):
                lines.append(f"  - {step.get('name')}: {step.get('conclusion', 'unknown')}")
        return "\n".join(lines)

    def merge_pull_request(self, pr_number: int, project_name: str) -> str:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/pulls/{pr_number}/merge"
        payload = {
            "commit_title": f"Merge {project_name}",
            "merge_method": "merge",
        }
        resp = requests.put(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        return resp.json().get("sha", "")

    def close_pull_request(self, pr_number: int) -> None:
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/pulls/{pr_number}"
        payload = {"state": "closed"}
        resp = requests.patch(url, headers=self.headers, json=payload)
        resp.raise_for_status()

    def ensure_standard_pipeline(self) -> bool:
        from agent.standard_pipeline import PIPELINE_VERSION, get_standard_pipeline

        pipeline_path = ".github/workflows/terraform-standard.yml"
        content = get_standard_pipeline()
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/contents/{pipeline_path}"
        resp = requests.get(url, headers=self.headers, params={"ref": self._get_default_branch()})

        if resp.status_code == 200:
            existing = base64.b64decode(resp.json()["content"]).decode("utf-8")
            if f"pipeline-version: {PIPELINE_VERSION}" in existing:
                return False

        self._create_or_update_file(
            path=pipeline_path,
            content=content,
            branch=self._get_default_branch(),
            commit_message=f"chore: update Terraform pipeline v{PIPELINE_VERSION}",
        )
        return True

    def bootstrap_infra_repo(self) -> bool:
        """Pousse le squelette terraform/ si absent."""
        marker = f"{TF_ROOT}/main.tf"
        url = f"{self.api_url}/repos/{self.owner}/{self.repo}/contents/{marker}"
        resp = requests.get(url, headers=self.headers, params={"ref": self._get_default_branch()})
        if resp.status_code == 200:
            return False

        branch = self._get_default_branch()
        files = get_bootstrap_files()
        msg = "chore: bootstrap infra-provisioned terraform project"
        for path, body in files.items():
            self._create_or_update_file(path, body, branch, msg)
        return True

    def get_repo_context(self) -> Dict[str, str]:
        """Lit tous les fichiers .tf du repo (récursif, priorité terraform/)."""
        branch = self._get_default_branch()
        sha = self._get_branch_sha(branch)
        tree_url = f"{self.api_url}/repos/{self.owner}/{self.repo}/git/trees/{sha}"
        resp = requests.get(tree_url, headers=self.headers, params={"recursive": "1"})
        if not resp.ok:
            return {}

        files: Dict[str, str] = {}
        for item in resp.json().get("tree", []):
            path = item.get("path", "")
            if item.get("type") != "blob" or not path.endswith(".tf"):
                continue
            if not path.startswith(f"{TF_ROOT}/") and "/" in path:
                continue
            file_url = (
                f"{self.api_url}/repos/{self.owner}/{self.repo}/contents/{path}"
                f"?ref={branch}"
            )
            fr = requests.get(file_url, headers=self.headers)
            if not fr.ok:
                continue
            data = fr.json()
            if data.get("encoding") == "base64":
                raw = base64.b64decode(data["content"]).decode("utf-8")
            else:
                dl = requests.get(data.get("download_url", ""), headers=self.headers)
                if not dl.ok:
                    continue
                raw = dl.text
            key = path.replace(f"{TF_ROOT}/", "") if path.startswith(f"{TF_ROOT}/") else path
            files[key] = raw

        return files
