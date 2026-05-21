"""
openai_client.py — Interface avec Azure OpenAI

Deux modes de génération :
  - Mode INCRÉMENTAL (fichiers existants) : LLM génère uniquement les nouveaux blocs HCL,
    Python les ajoute dans main.tf et variables.tf existants. Aucun nouveau fichier .tf créé.
  - Mode CRÉATION (premier ticket) : LLM génère un projet Terraform complet.

Pipeline commun (couche 2 + 3) :
  - Post-traitement Python : supprime les attributs azurerm invalides
  - Validation LLM : vérifie les dépendances et références
"""

import json
import re
from dataclasses import dataclass, field
from openai import AzureOpenAI

from agent.config import AgentConfig


# ── Structures de données ──────────────────────────────────────────────────────

@dataclass
class ResourceSpec:
    type: str
    name: str
    parameters: dict = field(default_factory=dict)


@dataclass
class InfraAnalysis:
    summary: str
    project_name: str
    environment: str
    location: str
    resources: list[ResourceSpec] = field(default_factory=list)
    naming_prefix: str = "infra-prov"
    tags: dict = field(default_factory=dict)


# ── Système prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Tu es un expert Azure et Terraform. Tu produis du code Terraform VALIDE et COMPATIBLE azurerm ~> 3.90.

Règles générales :
- Utilise TOUJOURS azurerm ~> 3.90 (jamais >= 3.90 qui autoriserait la 4.x)
- Toutes les variables doivent avoir un default
- Jamais de secrets en dur
- Références Terraform TOUJOURS : virtual_network_name = azurerm_virtual_network.main.name
- Si tu crées azurerm_subnet → tu DOIS créer azurerm_virtual_network
- Si tu crées azurerm_virtual_network → tu DOIS créer azurerm_resource_group
- N'invente jamais qu'une ressource "existe déjà" si elle n'est pas dans le contexte fourni
- Ne génère JAMAIS de bloc backend dans providers.tf

ATTRIBUTS INTERDITS (INVALIDES EN AZURERM 3.x) :
- azurerm_subnet : tags, private_endpoint_network_policies_enabled,
  enforce_private_link_endpoint_network_policies, enforce_private_link_service_network_policies
- azurerm_network_security_rule : tags
- azurerm_route : tags
- azurerm_role_assignment : tags
- azurerm_private_dns_zone_virtual_network_link : tags
- azurerm_subnet_network_security_group_association : tags
- azurerm_virtual_network_peering : tags
"""


# ── Post-traitement déterministe (couche 2) ────────────────────────────────────

_INVALID_ATTRIBUTES: dict[str, frozenset[str]] = {
    "azurerm_subnet": frozenset({
        "tags",
        "private_endpoint_network_policies_enabled",
        "enforce_private_link_endpoint_network_policies",
        "enforce_private_link_service_network_policies",
    }),
    "azurerm_network_security_rule": frozenset({"tags"}),
    "azurerm_route": frozenset({"tags"}),
    "azurerm_role_assignment": frozenset({"tags"}),
    "azurerm_private_dns_zone_virtual_network_link": frozenset({"tags"}),
    "azurerm_subnet_network_security_group_association": frozenset({"tags"}),
    "azurerm_virtual_network_peering": frozenset({"tags"}),
    "azurerm_network_interface_security_group_association": frozenset({"tags"}),
    "azurerm_lb_backend_address_pool_association": frozenset({"tags"}),
}

_ATTR_RE = re.compile(r"^\s*([\w]+)\s*=")


def _fix_tf_content(content: str) -> tuple[str, list[str]]:
    """Supprime les attributs invalides dans un contenu HCL."""
    lines = content.split("\n")
    result: list[str] = []
    fixes: list[str] = []
    current_resource: str | None = None
    depth = 0

    for lineno, line in enumerate(lines, 1):
        m = re.match(r'\s*resource\s+"(\w+)"\s+"\w+"\s*\{', line)
        if m:
            current_resource = m.group(1)
            depth = 1
            result.append(line)
            continue

        if current_resource is not None:
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                current_resource = None
                depth = 0
                result.append(line)
                continue

            invalid = _INVALID_ATTRIBUTES.get(current_resource)
            if invalid:
                attr_match = _ATTR_RE.match(line)
                if attr_match and attr_match.group(1) in invalid:
                    fixes.append(
                        f"L{lineno}: '{attr_match.group(1)}' supprimé de '{current_resource}'"
                    )
                    continue

        result.append(line)

    return "\n".join(result), fixes


def _post_process(files: dict[str, str]) -> dict[str, str]:
    corrected: dict[str, str] = {}
    all_fixes: list[str] = []

    for fname, content in files.items():
        if fname.endswith(".tf"):
            fixed, fixes = _fix_tf_content(content)
            corrected[fname] = fixed
            all_fixes.extend(f"[{fname}] {f}" for f in fixes)
        else:
            corrected[fname] = content

    if all_fixes:
        print(f"\n  🔧 Post-traitement — {len(all_fixes)} correction(s) :")
        for fix in all_fixes:
            print(f"     • {fix}")

    return corrected


# ── Client OpenAI ──────────────────────────────────────────────────────────────

class OpenAIClient:

    def __init__(self, config: AgentConfig):
        self.client = AzureOpenAI(
            azure_endpoint=config.azure_openai_endpoint,
            api_key=config.azure_openai_api_key,
            api_version=config.azure_openai_api_version,
        )
        self.deployment = config.azure_openai_deployment
        self.config = config

    # ── Analyse de la description ──────────────────────────────────────────────

    def analyze_description(
        self,
        description: str,
        existing_tf: dict[str, str] | None = None,
    ) -> InfraAnalysis:
        existing_context = ""
        if existing_tf:
            files_summary = "\n\n".join(
                f"### {fname}\n```hcl\n{content[:800]}{'...' if len(content) > 800 else ''}\n```"
                for fname, content in existing_tf.items()
            )
            existing_context = f"""
Infrastructure déjà déployée :
{files_summary}
Ne recrée pas ces ressources.
"""

        prompt = f"""
Analyse la demande et retourne UNIQUEMENT un JSON valide.
{existing_context}
Demande : {description}

Format :
{{
  "summary": "Résumé clair",
  "project_name": "slug-sans-espaces",
  "environment": "dev|staging|prod",
  "location": "germanywestcentral",
  "naming_prefix": "projet-env",
  "tags": {{"project": "...", "environment": "...", "owner": "devops-team"}},
  "resources": [
    {{"type": "vm|database|storage|network|keyvault|openai|aks", "name": "nom-logique", "parameters": {{}}}}
  ]
}}

Inclus TOUJOURS "network" si d'autres ressources en ont besoin.
"""
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        resources = [
            ResourceSpec(type=r["type"], name=r["name"], parameters=r.get("parameters", {}))
            for r in data.get("resources", [])
        ]
        return InfraAnalysis(
            summary=data.get("summary", ""),
            project_name=data.get("project_name", "infra-projet"),
            environment=data.get("environment", self.config.default_environment),
            location=data.get("location", self.config.default_location),
            naming_prefix=data.get("naming_prefix", self.config.naming_prefix),
            tags=data.get("tags", {}),
            resources=resources,
        )

    # ── Point d'entrée de la génération ───────────────────────────────────────

    def generate_terraform(
        self,
        analysis: InfraAnalysis,
        existing_tf: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """
        Choix du mode selon la présence de fichiers existants :
          - Fichiers existants → mode INCRÉMENTAL (ajoute dans main.tf + variables.tf)
          - Pas de fichiers    → mode CRÉATION (projet complet)
        """
        if existing_tf:
            files = self._generate_incremental(analysis, existing_tf)
        else:
            files = self._generate_full_project(analysis)

        files = _post_process(files)
        files = self._validate_and_correct(files)
        files["README.md"] = self._generate_readme(analysis, list(files.keys()))
        return files

    # ── Mode INCRÉMENTAL ───────────────────────────────────────────────────────

    def _generate_incremental(
        self,
        analysis: InfraAnalysis,
        existing_tf: dict[str, str],
    ) -> dict[str, str]:
        """
        Lit main.tf + variables.tf existants depuis main.
        Demande au LLM UNIQUEMENT les nouveaux blocs HCL.
        Python les ajoute dans les fichiers existants — aucun nouveau .tf créé.
        """
        files_summary = "\n\n".join(
            f"### {fname}\n```hcl\n{content}\n```"
            for fname, content in existing_tf.items()
            if fname.endswith(".tf")
        )

        resources_desc = json.dumps(
            [{"type": r.type, "name": r.name, "parameters": r.parameters}
             for r in analysis.resources],
            indent=2,
        )

        prompt = f"""
Voici les fichiers Terraform EXISTANTS du projet (branche main) :

{files_summary}

Tu dois ajouter les ressources suivantes à ce projet.
Projet : {analysis.project_name} | Env : {analysis.environment} | Région : {analysis.location}
Préfixe : {analysis.naming_prefix} | Tags : {json.dumps(analysis.tags)}
Nouvelles ressources : {resources_desc}

Retourne UNIQUEMENT un JSON avec ces 4 clés :
{{
  "new_resources": "UNIQUEMENT les nouveaux blocs resource{{...}} HCL à ajouter dans main.tf",
  "new_variables": "UNIQUEMENT les nouveaux blocs variable{{...}} HCL (pas ceux qui existent déjà)",
  "new_outputs": "UNIQUEMENT les nouveaux blocs output{{...}} HCL (vide si aucun)",
  "tfvars_lines": "nouvelles lignes clé = valeur pour terraform.tfvars (vide si aucune)"
}}

RÈGLES STRICTES :
- NE PAS inclure providers.tf ni les blocs terraform{{}}
- NE PAS redéclarer les variables déjà présentes dans variables.tf
- Réutilise var.naming_prefix, var.location, var.tags sans les redéclarer
- Utilise des références Terraform (azurerm_resource.name.attr) jamais de noms en dur
- Si un subnet est nécessaire, inclus le VNet dans new_resources
- Si un VNet est nécessaire, inclus le Resource Group dans new_resources (sauf s'il existe déjà)
"""

        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        incremental = json.loads(response.choices[0].message.content)

        # ── Fusionner dans les fichiers existants ──────────────────────────────
        files: dict[str, str] = {}

        new_resources = incremental.get("new_resources", "").strip()
        if new_resources:
            base_main = existing_tf.get("main.tf", "")
            files["main.tf"] = base_main + "\n\n" + new_resources

        new_variables = incremental.get("new_variables", "").strip()
        if new_variables:
            base_vars = existing_tf.get("variables.tf", "")
            files["variables.tf"] = base_vars + "\n\n" + new_variables

        new_outputs = incremental.get("new_outputs", "").strip()
        if new_outputs:
            base_outputs = existing_tf.get("outputs.tf", "")
            files["outputs.tf"] = base_outputs + "\n\n" + new_outputs

        # terraform.tfvars : base + nouvelles valeurs
        base_tfvars = existing_tf.get("terraform.tfvars", "")
        tfvars_lines = incremental.get("tfvars_lines", "").strip()
        if not base_tfvars:
            base_tfvars = (
                f'naming_prefix = "{analysis.naming_prefix}"\n'
                f'location      = "{analysis.location}"\n'
                f'environment   = "{analysis.environment}"\n'
            )
        files["terraform.tfvars"] = (
            base_tfvars + ("\n" + tfvars_lines if tfvars_lines else "")
        )

        return files

    # ── Mode CRÉATION (premier ticket, aucun fichier existant) ────────────────

    def _generate_full_project(self, analysis: InfraAnalysis) -> dict[str, str]:
        """Génère un projet Terraform complet quand le repo est vide."""
        resources_desc = json.dumps(
            [{"type": r.type, "name": r.name, "parameters": r.parameters}
             for r in analysis.resources],
            indent=2,
        )
        tfvars = (
            f'naming_prefix = "{analysis.naming_prefix}"\n'
            f'location      = "{analysis.location}"\n'
            f'environment   = "{analysis.environment}"\n'
        )
        prompt = f"""
Crée un projet Terraform Azure complet : providers.tf, variables.tf, main.tf, outputs.tf, terraform.tfvars
Pas de bloc backend dans providers.tf. Version azurerm ~> 3.90.

Projet : {analysis.project_name} | Env : {analysis.environment} | Région : {analysis.location}
Préfixe : {analysis.naming_prefix} | Tags : {json.dumps(analysis.tags)}
Ressources : {resources_desc}

Retourne un JSON {{nom_fichier: contenu_hcl}}.
terraform.tfvars doit contenir au minimum :
{tfvars}
"""
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=8000,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    # ── Couche 3 : Validation LLM ──────────────────────────────────────────────

    def _validate_and_correct(self, files: dict[str, str]) -> dict[str, str]:
        """Vérifie dépendances, références en dur, attributs invalides. Corrige si nécessaire."""
        tf_content = "\n\n".join(
            f"### {fname}\n```hcl\n{content}\n```"
            for fname, content in files.items()
            if fname.endswith(".tf")
        )
        if not tf_content.strip():
            return files

        prompt = f"""
Vérifie et corrige ce code Terraform Azure.

{tf_content}

Points à vérifier et corriger :
1. azurerm_subnet présent → azurerm_virtual_network doit exister
2. azurerm_virtual_network présent → azurerm_resource_group doit exister
3. Aucune référence en dur : virtual_network_name = "nom" → azurerm_virtual_network.X.name
4. azurerm_subnet : supprimer tags, private_endpoint_network_policies_enabled
5. azurerm_network_security_rule, azurerm_route, azurerm_role_assignment : supprimer tags
6. Toutes les var.X utilisées doivent être déclarées avec un default dans variables.tf

Retourne {{nom_fichier: contenu_complet}} UNIQUEMENT pour les fichiers modifiés.
Si tout est correct → retourne {{}}.
"""
        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": "Expert Terraform. Valide et corrige. Réponds en JSON uniquement."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=8000,
                response_format={"type": "json_object"},
            )
            corrections: dict[str, str] = json.loads(response.choices[0].message.content)
            if corrections:
                print(f"\n  ✅ Validation — {len(corrections)} fichier(s) corrigé(s) : {', '.join(corrections)}")
                for fname, content in corrections.items():
                    if fname.endswith((".tf", ".tfvars")):
                        files[fname] = content
            else:
                print("\n  ✅ Validation — code correct, aucune correction.")
        except Exception as e:
            print(f"\n  ⚠️  Validation ignorée : {e}")

        return files

    # ── README automatique ─────────────────────────────────────────────────────

    def _generate_readme(self, analysis: InfraAnalysis, tf_files: list[str]) -> str:
        resources_list = "\n".join(f"- **{r.type.upper()}** : `{r.name}`" for r in analysis.resources)
        return f"""# Infrastructure : {analysis.project_name}

> Généré automatiquement par l'Agent IA DevOps

## Résumé
{analysis.summary}

## Ressources Azure
{resources_list}

## Paramètres
| Paramètre | Valeur |
|-----------|--------|
| Région | `{analysis.location}` |
| Environnement | `{analysis.environment}` |
| Préfixe | `{analysis.naming_prefix}` |

## Déploiement
```bash
terraform init
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

## Fichiers modifiés
{chr(10).join(f'- `{f}`' for f in tf_files)}

## Tags
```json
{json.dumps(analysis.tags, indent=2)}
```
"""
