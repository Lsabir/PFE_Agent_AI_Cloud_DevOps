"""
llm_engine.py — Moteur Azure OpenAI
Analyse une description, identifie les ressources Azure,
génère le code Terraform complet avec bonnes pratiques.

Endpoint utilisé (depuis la VM via Private Endpoint) :
  https://infra-agent-ai-openai.openai.azure.com/
  → Résolution DNS : privatelink.openai.azure.com → IP privée subnet-PE
"""

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AzureOpenAI, RateLimitError, APITimeoutError, APIError

from agent.config import Config

log = logging.getLogger(__name__)


# ── Structures de données ──────────────────────────────────────────────────────

@dataclass
class AzureResource:
    resource_type: str
    logical_name:  str
    parameters:    dict = field(default_factory=dict)

    def __str__(self) -> str:
        p = ", ".join(f"{k}={v}" for k, v in self.parameters.items())
        return f"{self.resource_type.upper()} '{self.logical_name}'" + (f" ({p})" if p else "")


@dataclass
class InfraRequest:
    project_slug:   str
    environment:    str
    location:       str
    naming_prefix:  str
    summary:        str
    resources:      list[AzureResource] = field(default_factory=list)
    tags:           dict                = field(default_factory=dict)


@dataclass
class TerraformProject:
    files:    dict[str, str] = field(default_factory=dict)
    warnings: list[str]      = field(default_factory=list)




_SYS_ANALYST = """
Tu es un architecte Azure senior. Tu analyses des demandes d'infrastructure
en langage naturel et retournes une structure JSON précise.
Règles :
- Identifie TOUTES les ressources (VM, DB, réseau, stockage, etc.)
- Inclus toujours une ressource "network" si d'autres ressources en ont besoin
- Déduis l'environnement (dev/staging/prod) depuis le contexte
- Région par défaut : germanywestcentral (conformité RGPD)
- project_slug en kebab-case sans majuscules
"""

_SYS_TERRAFORM = """
Tu es un expert Terraform et Azure. Tu génères du code HCL de production.
Règles STRICTES :
1. providers.tf  → azurerm >= 3.90, Terraform >= 1.5, backend azurerm commenté
2. variables.tf  → toutes les valeurs configurables, descriptions en français,
                   validations si nécessaire, jamais de secrets en default
3. main.tf       → locals{tags}, resource_group, modules commentés par section,
                   SystemAssigned identity sur les VMs, Private Endpoints pour PaaS
4. outputs.tf    → IDs, URIs, IPs, noms utiles
5. terraform.tfvars.example → valeurs fictives commentées, aucun secret réel

Retourne UNIQUEMENT un JSON dont les clés sont les noms de fichiers.
"""


# ── Définitions Function Calling ───────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_infra_request",
            "description": "Crée une demande d'infrastructure structurée",
            "parameters": {
                "type": "object",
                "required": ["project_slug", "environment", "location",
                             "naming_prefix", "summary", "resources", "tags"],
                "properties": {
                    "project_slug":  {"type": "string"},
                    "environment":   {"type": "string", "enum": ["dev", "staging", "prod"]},
                    "location":      {"type": "string"},
                    "naming_prefix": {"type": "string"},
                    "summary":       {"type": "string"},
                    "tags":          {"type": "object"},
                    "resources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["resource_type", "logical_name", "parameters"],
                            "properties": {
                                "resource_type": {
                                    "type": "string",
                                    "enum": [
                                        "network", "vm", "database_postgres",
                                        "database_mysql", "database_mssql",
                                        "storage_account", "key_vault",
                                        "container_registry", "aks",
                                        "app_service", "function_app",
                                        "service_bus", "redis"
                                    ]
                                },
                                "logical_name": {"type": "string"},
                                "parameters":   {"type": "object"}
                            }
                        }
                    }
                }
            }
        }
    }
]


# ── Moteur LLM ─────────────────────────────────────────────────────────────────

class LLMEngine:

    def __init__(self, config: Config):
        self._cfg = config
        self._client = AzureOpenAI(
            azure_endpoint=config.openai_endpoint,
            api_key=config.openai_api_key,
            api_version=config.openai_api_version,
        )
        self._model = config.openai_deployment
        log.info(f"Azure OpenAI : {config.openai_endpoint} / {self._model}")

 
 


    def ping(self) -> bool:
        """Vérifie que l'endpoint Azure OpenAI répond."""
        try:
            r = self._call(
                messages=[{"role": "user", "content": "Réponds uniquement 'ok'"}],
                max_tokens=5, temperature=0.0
            )
            log.info(f"Ping OpenAI → '{r.choices[0].message.content.strip()}'")
            return True
        except Exception as e:
            log.error(f"Ping échoué : {e}")
            return False




    def analyze(self, description: str) -> InfraRequest:
        """Analyse la description et retourne un InfraRequest structuré."""
        log.info("Analyse de la description en cours...")

        r = self._call(
            messages=[
                {"role": "system", "content": _SYS_ANALYST},
                {"role": "user",   "content": f"Infrastructure souhaitée :\n\n{description}"},
            ],
            tools=_TOOLS,
            tool_choice={"type": "function", "function": {"name": "create_infra_request"}},
            max_tokens=1500, temperature=0.0
        )

        args = json.loads(r.choices[0].message.tool_calls[0].function.arguments)

        resources = [
            AzureResource(
                resource_type=res["resource_type"],
                logical_name=res["logical_name"],
                parameters=res.get("parameters", {}),
            )
            for res in args.get("resources", [])
        ]

        return InfraRequest(
            project_slug=args["project_slug"],
            environment=args["environment"],
            location=args["location"],
            naming_prefix=args["naming_prefix"],
            summary=args["summary"],
            tags=args.get("tags", {}),
            resources=resources,
        )




    def generate_terraform(self, req: InfraRequest) -> TerraformProject:
        """Génère les fichiers Terraform pour le InfraRequest."""
        log.info("Génération du code Terraform...")

        resources_json = json.dumps(
            [{"type": r.resource_type, "name": r.logical_name, "params": r.parameters}
             for r in req.resources],
            indent=2, ensure_ascii=False
        )

        r = self._call(
            messages=[
                {"role": "system", "content": _SYS_TERRAFORM},
                {"role": "user", "content": f"""
Génère un projet Terraform Azure complet.

project_slug  : {req.project_slug}
environment   : {req.environment}
location      : {req.location}
naming_prefix : {req.naming_prefix}
tags          : {json.dumps(req.tags, ensure_ascii=False)}

Ressources :
{resources_json}

Fichiers à générer (JSON, clés = noms de fichiers) :
{{ "providers.tf":"...", "variables.tf":"...", "main.tf":"...",
   "outputs.tf":"...", "terraform.tfvars.example":"..." }}

Retourne UNIQUEMENT le JSON, sans markdown.
"""},
            ],
            response_format={"type": "json_object"},
            max_tokens=4000, temperature=0.0
        )

        files = json.loads(r.choices[0].message.content)
        files["README.md"] = self._readme(req, list(files.keys()))

        project = TerraformProject(files=files)

        if "private_endpoint" not in files.get("main.tf", "").lower():
            project.warnings.append("⚠ Private Endpoint non détecté — recommandé pour les services PaaS")

        log.info(f"Génération terminée : {len(files)} fichiers")
        return project

  
  

    def summarize_plan(self, plan_output: str) -> str:
        """Résume le terraform plan en langage humain clair."""
        if not plan_output or len(plan_output) < 50:
            return "(plan non disponible)"
        try:
            r = self._call(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es expert Azure/Terraform. Résume ce plan en 3-5 phrases "
                            "claires pour un opérateur. Indique le nombre de ressources "
                            "créées/modifiées/supprimées et les risques éventuels."
                        )
                    },
                    {"role": "user", "content": f"Plan :\n\n{plan_output[:3000]}"}
                ],
                max_tokens=400, temperature=0.2
            )
            return r.choices[0].message.content
        except Exception as e:
            log.warning(f"Résumé du plan impossible : {e}")
            return plan_output[:500]

  
  

    def refine(self, project: TerraformProject, feedback: str) -> TerraformProject:
        """Raffine le code Terraform selon le retour de l'opérateur."""
        log.info("Raffinement en cours...")
        r = self._call(
            messages=[
                {"role": "system", "content": _SYS_TERRAFORM},
                {"role": "user", "content": f"""
main.tf actuel :
```hcl
{project.files.get('main.tf', '')[:2000]}
```
variables.tf actuel :
```hcl
{project.files.get('variables.tf', '')[:1000]}
```
Modification demandée : {feedback}

Retourne le JSON complet mis à jour.
"""},
            ],
            response_format={"type": "json_object"},
            max_tokens=4000, temperature=0.0
        )
        updated = json.loads(r.choices[0].message.content)
        project.files.update(updated)
        project.warnings.clear()
        return project





    def _call(self, messages: list, max_tokens: int, temperature: float,
              tools=None, tool_choice=None, response_format=None,
              max_retries: int = 3):
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,


            
            "max_completion_tokens": max_tokens,



            
        }
        if tools:          kwargs["tools"]           = tools
        if tool_choice:    kwargs["tool_choice"]     = tool_choice
        if response_format: kwargs["response_format"] = response_format

        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                return self._client.chat.completions.create(**kwargs)
            except (RateLimitError, APITimeoutError) as e:
                wait = 2 ** attempt
                log.warning(f"Retry {attempt}/{max_retries} dans {wait}s — {e}")
                time.sleep(wait)
                last_err = e
            except APIError as e:
                log.error(f"Azure OpenAI erreur {e.status_code} : {e.message}")
                raise

        raise RuntimeError(f"Azure OpenAI inaccessible après {max_retries} tentatives : {last_err}")





    def _readme(self, req: InfraRequest, files: list[str]) -> str:
        rows = "\n".join(
            f"| `{r.resource_type}` | `{r.logical_name}` | "
            f"{', '.join(f'`{k}={v}`' for k, v in r.parameters.items()) or '—'} |"
            for r in req.resources
        )
        return f"""# Infrastructure : {req.project_slug}

> Généré par l'Agent IA DevOps

## Résumé
{req.summary}

## Ressources Azure
| Type | Nom | Paramètres |
|------|-----|------------|
{rows}

## Paramètres
| | |
|-|-|
| Région | `{req.location}` |
| Environnement | `{req.environment}` |
| Préfixe | `{req.naming_prefix}` |

## Déploiement
```bash
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform validate
terraform plan -var-file=terraform.tfvars -out=tfplan
terraform apply tfplan
```

## Fichiers
{chr(10).join(f'- `{f}`' for f in files)}
"""