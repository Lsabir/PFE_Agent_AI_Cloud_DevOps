"""
openai_client.py — Interface avec Azure OpenAI
Analyse la description, identifie les ressources et génère le code Terraform.
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from openai import AzureOpenAI

from agent.config import AgentConfig


# ── Structures de données ──────────────────────────────────────────────────────

@dataclass
class ResourceSpec:
    """Représente une ressource Azure identifiée depuis la description."""
    type: str           # "vm", "database", "storage", "network", "keyvault", "openai"
    name: str           # nom logique
    parameters: dict = field(default_factory=dict)


@dataclass
class InfraAnalysis:
    """Résultat de l'analyse de la description par le LLM."""
    summary: str                              # résumé humain de ce qui sera créé
    project_name: str                         # nom du projet (slug)
    environment: str                          # dev / staging / prod
    location: str                             # région Azure
    resources: list[ResourceSpec] = field(default_factory=list)
    naming_prefix: str = "infra-prov"
    tags: dict = field(default_factory=dict)


# ── Système prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Tu es un expert Azure et Terraform. Tu travailles sur des projets Terraform EXISTANTS.
Ton rôle est d'analyser des demandes d'infrastructure et de produire le code Terraform
MODIFIÉ ou NOUVEAU, compatible avec le projet existant.

Règles strictes :
- Utilise toujours azurerm provider >= 3.90 et Terraform >= 1.5
- Applique des tags sur toutes les ressources (project, environment, owner)
- Ne duplique JAMAIS les ressources/variables/providers déjà présents dans le projet
- Nomme les ressources avec un préfixe configurable via variable (réutilise var.naming_prefix si elle existe déjà)
- Ne mets jamais de secrets ou de mots de passe en dur dans le code
- Respecte le principe du moindre privilège pour les rôles RBAC
- Active soft_delete sur Key Vault, disable public access sur les services sensibles
- Quand des fichiers .tf existent déjà, MODIFIE-LES directement pour y intégrer les nouvelles ressources
- Ne crée PAS de nouveau fichier séparé si les nouvelles ressources peuvent être ajoutées dans main.tf ou variables.tf existants
- Toutes les variables déclarées doivent avoir une valeur par défaut (default = "...")
- Ne génère JAMAIS de bloc backend dans providers.tf (le backend est géré par le pipeline CI/CD)

RÈGLES CRITIQUES SUR LES DÉPENDANCES — NE JAMAIS VIOLER :
- JAMAIS de nom de ressource Azure écrit en dur dans un attribut de référence (ex: virtual_network_name = "vnet-existing" est INTERDIT)
- Utilise TOUJOURS les références Terraform : virtual_network_name = azurerm_virtual_network.main.name
- Si tu crées un subnet, tu DOIS créer le azurerm_virtual_network dans le même code
- Si tu crées une ressource qui dépend d'un resource group, tu DOIS créer le azurerm_resource_group dans le même code (sauf s'il existe déjà dans existing_tf)
- Si tu crées une resource qui dépend d'un VNet et que ce VNet N'EST PAS dans existing_tf, tu DOIS le créer
- N'invente jamais qu'une ressource Azure "existe déjà" si elle n'est pas dans existing_tf

RESSOURCES AZURE QUI NE SUPPORTENT PAS `tags` — NE JAMAIS METTRE tags SUR CES RESSOURCES :
- azurerm_subnet (PAS de tags)
- azurerm_network_security_rule (PAS de tags — mettre tags sur azurerm_network_security_group)
- azurerm_route (PAS de tags — mettre tags sur azurerm_route_table)
- azurerm_role_assignment (PAS de tags)
- azurerm_private_dns_zone_virtual_network_link (PAS de tags)
- azurerm_subnet_network_security_group_association (PAS de tags)
- azurerm_virtual_network_peering (PAS de tags)
"""


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

    def analyze_description(self, description: str, existing_tf: dict[str, str] | None = None) -> InfraAnalysis:
        """
        Envoie la description au LLM et récupère une analyse JSON structurée
        des ressources Azure à créer.
        existing_tf : fichiers .tf existants du projet (peut être vide ou None).
        """
        existing_context = ""
        if existing_tf:
            files_summary = "\n\n".join(
                f"### {fname}\n```hcl\n{content[:800]}{'...' if len(content) > 800 else ''}\n```"
                for fname, content in existing_tf.items()
            )
            existing_context = f"""
CONTEXTE — Infrastructure déjà déployée dans ce projet :
{files_summary}

Tiens compte de ces ressources existantes : ne les recrée pas, réutilise leurs
noms/IDs si la nouvelle demande en dépend, et signale toute mise à jour nécessaire.
"""

        prompt = f"""
Analyse la demande d'infrastructure suivante et retourne UNIQUEMENT un JSON valide.
{existing_context}
Demande : {description}

Format JSON attendu :
{{
  "summary": "Résumé clair de ce qui sera créé",
  "project_name": "slug-sans-espaces",
  "environment": "dev|staging|prod",
  "location": "germanywestcentral",
  "naming_prefix": "projet-env",
  "tags": {{"project": "...", "environment": "...", "owner": "devops-team"}},
  "resources": [
    {{
      "type": "vm|database|storage|network|keyvault|openai|container|aks",
      "name": "nom-logique",
      "parameters": {{
        "vm_size": "Standard_B2s",
        "os": "ubuntu-22.04",
        "...": "..."
      }}
    }}
  ]
}}

Inclus TOUJOURS un réseau (type: "network") si d'autres ressources en ont besoin.
"""
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        data = json.loads(raw)
        

        resources = [
            ResourceSpec(
                type=r["type"],
                name=r["name"],
                parameters=r.get("parameters", {}),
            )
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

    # ── Génération du code Terraform ───────────────────────────────────────────

    def generate_terraform(self, analysis: InfraAnalysis, existing_tf: dict[str, str] | None = None) -> dict[str, str]:
        """
        Génère les fichiers Terraform complets basés sur l'analyse.
        Retourne un dict {nom_fichier: contenu}.
        existing_tf : fichiers .tf existants à fusionner/mettre à jour.
        """
        resources_desc = json.dumps(
            [{"type": r.type, "name": r.name, "parameters": r.parameters}
             for r in analysis.resources],
            indent=2
        )

        existing_context = ""
        if existing_tf:
            files_summary = "\n\n".join(
                f"### {fname}\n```hcl\n{content}\n```"
                for fname, content in existing_tf.items()
            )
            existing_context = f"""
PROJET TERRAFORM EXISTANT — lis TOUT le code ci-dessous avant de générer quoi que ce soit :

{files_summary}

RÈGLES CRITIQUES :
1. Intègre les nouvelles ressources DIRECTEMENT dans les fichiers existants (main.tf, variables.tf, outputs.tf).
2. Retourne chaque fichier MODIFIÉ avec son contenu COMPLET (ancien code + nouveau code ensemble).
3. Ne crée pas de nouveau fichier séparé sauf si c'est un module entièrement nouveau.
4. Réutilise les variables existantes (var.naming_prefix, var.location, var.tags...) sans les redéclarer.
5. Ne régénère PAS providers.tf s'il existe déjà.
"""
        else:
            existing_context = """
Génère un projet Terraform complet avec : providers.tf, variables.tf, main.tf, outputs.tf
IMPORTANT : Ne génère PAS de bloc backend dans providers.tf (le backend est géré par le pipeline CI/CD).
"""

        tfvars_values = f"""naming_prefix = "{analysis.naming_prefix}"
location      = "{analysis.location}"
environment   = "{analysis.environment}"
"""

        prompt = f"""
{'Modifie le projet Terraform existant' if existing_tf else 'Crée un nouveau projet Terraform Azure'} pour provisionner les ressources suivantes.
{existing_context}
Projet : {analysis.project_name}
Environnement : {analysis.environment}
Région : {analysis.location}
Préfixe : {analysis.naming_prefix}
Tags : {json.dumps(analysis.tags)}
Ressources à créer : {resources_desc}

Retourne un JSON {{nom_fichier: contenu_hcl}} contenant :
- Les fichiers MODIFIÉS avec leur contenu COMPLET (si fichiers existants)
- Le fichier terraform.tfvars avec au minimum :
{tfvars_values}

Règles :
- azurerm >= 3.90, Terraform >= 1.5
- Tags sur toutes les ressources
- Pas de secrets en dur
- RBAC moindre privilège
- Private Endpoints pour les services PaaS sensibles
- SystemAssigned Managed Identity si VM créée
- Toutes les variables doivent avoir un default
- Pas de bloc backend dans providers.tf
"""
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=8000,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        files = json.loads(raw)

        # Ajoute le README généré automatiquement
        files["README.md"] = self._generate_readme(analysis, list(files.keys()))

        return files

    # ── Génération du README ───────────────────────────────────────────────────

    def _generate_readme(self, analysis: InfraAnalysis, tf_files: list[str]) -> str:
        resources_list = "\n".join(
            f"- **{r.type.upper()}** : `{r.name}`" for r in analysis.resources
        )
        return f"""# Infrastructure : {analysis.project_name}

> Généré automatiquement par l'Agent IA DevOps

## Résumé

{analysis.summary}

## Ressources Azure créées

{resources_list}

## Paramètres

| Paramètre | Valeur |
|-----------|--------|
| Région | `{analysis.location}` |
| Environnement | `{analysis.environment}` |
| Préfixe | `{analysis.naming_prefix}` |

## Déploiement

```bash
# 1. Copier et renseigner les variables
cp terraform.tfvars.example terraform.tfvars
# Editer terraform.tfvars avec vos vraies valeurs

# 2. Initialiser Terraform
terraform init

# 3. Vérifier la configuration
terraform validate

# 4. Voir le plan
terraform plan -var-file=terraform.tfvars

# 5. Appliquer (après validation humaine)
terraform apply -var-file=terraform.tfvars
```

## Fichiers générés

{chr(10).join(f'- `{f}`' for f in tf_files)}

## Tags appliqués

```hcl
{json.dumps(analysis.tags, indent=2)}
```
"""
