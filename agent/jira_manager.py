"""
jira_manager.py — Intégration Jira pour l'Agent IA DevOps
Lit les tickets To Do, les passe In Progress, puis Done après validation.
"""

import requests
from requests.auth import HTTPBasicAuth
from typing import List, Dict, Optional


class JiraManager:
    def __init__(self, config):
        self.base_url = config.jira_url.rstrip("/")
        self.auth = HTTPBasicAuth(config.jira_email, config.jira_api_token)
        self.project_key = config.jira_project_key
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ── Lecture des tickets ──────────────────────────────────────────────────

    def get_todo_tickets(self) -> List[Dict]:
        """Récupère les tickets en statut 'To Do' du projet, triés par priorité."""
        jql = (
            f'project = "{self.project_key}" '
            f'AND status = "To Do" '
            f'ORDER BY priority ASC, created ASC'
        )
        url = f"{self.base_url}/rest/api/3/search/jql"
        params = {
            "jql": jql,
            "fields": "summary,description,status,assignee,priority",
            "maxResults": 20,
        }
        resp = requests.get(url, headers=self.headers, auth=self.auth, params=params)
        resp.raise_for_status()
        return resp.json().get("issues", [])

    def get_description(self, issue: Dict) -> str:
        """
        Retourne la description complète du ticket (summary + description).
        Gère le format Atlassian Document Format (ADF) utilisé par Jira Cloud.
        """
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        desc_field = fields.get("description")

        if not desc_field:
            return summary

        # Jira Cloud → format ADF (dict)
        if isinstance(desc_field, dict):
            body_text = self._extract_adf_text(desc_field)
        else:
            body_text = str(desc_field)

        if body_text:
            return f"{summary}\n\n{body_text}"
        return summary

    def _extract_adf_text(self, node: Dict) -> str:
        """Parcourt récursivement un nœud ADF et concatène le texte brut."""
        if node.get("type") == "text":
            return node.get("text", "")

        parts = []
        for child in node.get("content", []):
            part = self._extract_adf_text(child)
            if part:
                parts.append(part)

        separator = "\n" if node.get("type") in ("paragraph", "bulletList", "listItem", "heading") else " "
        return separator.join(parts).strip()

    # ── Transitions de statut ────────────────────────────────────────────────

    def _get_transitions(self, issue_key: str) -> List[Dict]:
        """Récupère toutes les transitions disponibles pour un ticket."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
        resp = requests.get(url, headers=self.headers, auth=self.auth)
        resp.raise_for_status()
        return resp.json().get("transitions", [])

    def _find_transition_id(self, issue_key: str, target_status: str) -> Optional[str]:
        """
        Cherche l'ID de transition vers target_status.
        Fait une correspondance exacte puis partielle (insensible à la casse).
        """
        transitions = self._get_transitions(issue_key)
        target_lower = target_status.lower()

        # 1. Correspondance exacte
        for t in transitions:
            if t["to"]["name"].lower() == target_lower:
                return t["id"]

        # 2. Correspondance partielle
        for t in transitions:
            if target_lower in t["to"]["name"].lower():
                return t["id"]

        return None

    def transition_to_in_progress(self, issue_key: str) -> bool:
        """Passe le ticket en 'In Progress'."""
        tid = self._find_transition_id(issue_key, "In Progress")
        if not tid:
            print(f"  ⚠️  Transition 'In Progress' introuvable pour {issue_key}.")
            return False
        return self._do_transition(issue_key, tid)

    def transition_to_done(self, issue_key: str) -> bool:
        """Passe le ticket en 'Done'."""
        for status_name in ("Done", "Closed", "Resolved"):
            tid = self._find_transition_id(issue_key, status_name)
            if tid:
                return self._do_transition(issue_key, tid)
        print(f"  ⚠️  Transition 'Done' introuvable pour {issue_key}.")
        return False

    def transition_to_todo(self, issue_key: str) -> bool:
        """Repasse le ticket en 'To Do' (en cas de refus)."""
        tid = self._find_transition_id(issue_key, "To Do")
        if not tid:
            return False
        return self._do_transition(issue_key, tid)

    def _do_transition(self, issue_key: str, transition_id: str) -> bool:
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions"
        payload = {"transition": {"id": transition_id}}
        resp = requests.post(url, json=payload, headers=self.headers, auth=self.auth)
        return resp.status_code in (200, 204)

    # ── Commentaires ─────────────────────────────────────────────────────────

    def add_comment(self, issue_key: str, text: str) -> None:
        """Ajoute un commentaire en format ADF au ticket."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": text}],
                    }
                ],
            }
        }
        requests.post(url, json=payload, headers=self.headers, auth=self.auth)
