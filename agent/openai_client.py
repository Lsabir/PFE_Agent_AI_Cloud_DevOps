"""
openai_client.py — Interface avec Azure OpenAI
Analyse la description, identifie les ressources et génère le code Terraform.

Pipeline de génération en 3 couches :
  1. LLM génère le code (generate_terraform)
  2. Post-traitement Python déterministe (_post_process) : corrige les erreurs connues sans LLM
  3. Second appel LLM de validation (_validate_and_correct) : vérifie les dépendances
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
Tu es un expert Azure et Terraform. Tu travailles sur des projets Terraform EXISTANTS.
Ton rôle est de produire du code Terraform VALIDE, COMPLET et COMPATIBLE avec le projet existant.

Règles générales :
- Utilise toujours azurerm provider >= 3.90 et Terraform >= 1.5
- Applique des tags sur toutes les ressources QUI LE SUPPORTENT (voir liste ci-dessous)
- Ne duplique JAMAIS les ressources/variables/providers déjà présents dans le projet
- Réutilise var.naming_prefix, var.location, var.tags si ces variables existent déjà
- Ne mets jamais de secrets ou de mots de passe en dur dans le code
- Respecte le principe du moindre privilège pour les rôles RBAC
- Active soft_delete sur Key Vault, disable public access sur les services sensibles
- Quand des fichiers .tf existent déjà, MODIFIE-LES pour y intégrer les nouvelles ressources
- Toutes les variables déclarées doivent avoir une valeur par défaut (default = "...")
- Ne génère JAMAIS de bloc backend dans providers.tf

RÈGLES CRITIQUES SUR LES DÉPENDANCES :
- JAMAIS de nom de ressource Azure écrit en dur dans un attribut de référence
  INTERDIT : virtual_network_name = "vnet-existing"
  CORRECT  : virtual_network_name = azurerm_virtual_network.main.name
- Si tu crées azurerm_subnet → tu DOIS créer azurerm_virtual_network dans le même fichier
- Si tu crées azurerm_virtual_network → tu DOIS créer azurerm_resource_group (sauf s'il existe dans existing_tf)
- N'invente jamais qu'une ressource Azure "existe déjà" si elle n'est pas dans existing_tf

ATTRIBUTS INTERDITS PAR RESSOURCE — NE JAMAIS UTILISER CES ATTRIBUTS :
- azurerm_subnet : PAS de tags, PAS de private_endpoint_network_policies_enabled,
  PAS de enforce_private_link_endpoint_network_policies, PAS de enforce_private_link_service_network_policies
- azurerm_network_security_rule : PAS de tags
- azurerm_route : PAS de tags
- azurerm_role_assignment : PAS de tags, PAS de scope (utiliser scope comme argument positionnel)
- azurerm_private_dns_zone_virtual_network_link : PAS de tags
- azurerm_subnet_network_security_group_association : PAS de tags
- azurerm_virtual_network_peering : PAS de tags
- azurerm_network_interface_security_group_association : PAS de tags
- azurerm_lb_backend_address_pool_association : PAS de tags

VERSION PROVIDER AZURERM : utilise TOUJOURS ~> 3.90 (pas >= 3.90) pour rester sur la 3.x
"""


# ── Post-traitement déterministe (couche 2) ────────────────────────────────────

# Attributs invalides par type de ressource azurerm (supprimés automatiquement)
_INVALID_ATTRIBUTES: dict[str, frozenset[str]] = {
    "azurerm_subnet": frozenset({
        "tags",
        "private_endpoint_network_policies_enabled",       # supprimé en azurerm 4.x
        "enforce_private_link_endpoint_network_policies",  # déprécié en azurerm 3.x
        "enforce_private_link_service_network_policies",   # déprécié en azurerm 3.x
    }),
    "azurerm_network_security_rule": frozenset({"tags"}),
    "azurerm_route": frozenset({"tags"}),
    "azurerm_role_assignment": frozenset({"tags"}),
    "azurerm_private_dns_zone_virtual_network_link": frozenset({"tags"}),
    "azurerm_subnet_network_security_group_association": frozenset({"tags"}),
    "azurerm_virtual_network_peering": frozenset({"tags"}),
    "azurerm_network_interface_security_group_association": frozenset({"tags"}),
    "azurerm_network_interface_backend_address_pool_association": frozenset({"tags"}),
    "azurerm_lb_backend_address_pool_association": frozenset({"tags"}),
}

# Regex pour détecter le nom de l'attribut sur une ligne HCL
_ATTR_RE = re.compile(r"^\s*([\w]+)\s*=")


def _fix_tf_content(content: str) -> tuple[str, list[str]]:
    """
    Corrige les erreurs connues dans un contenu HCL.
    Supprime les attributs invalides listés dans _INVALID_ATTRIBUTES.
    Retourne (contenu_corrigé, liste_des_corrections).
    """
    lines = content.split("\n")
    result: list[str] = []
    fixes: list[str] = []

    current_resource: str | None = None
    depth = 0

    for lineno, line in enumerate(lines, 1):
        # Détecter l'ouverture d'un bloc resource
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

            # Supprimer les attributs invalides pour ce type de ressource
            invalid = _INVALID_ATTRIBUTES.get(current_resource)
            if invalid:
                attr_match = _ATTR_RE.match(line)
                if attr_match and attr_match.group(1) in invalid:
                    fixes.append(
                        f"L{lineno}: '{attr_match.group(1)}' supprimé de '{current_resource}'"
                        f" (attribut non supporté par azurerm)"
                    )
                    continue

        result.append(line)

    return "\n".join(result), fixes


def _post_process(files: dict[str, str]) -> dict[str, str]:
    """Applique _fix_tf_content sur tous les fichiers .tf et affiche un rapport."""
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
        print(f"\n  🔧 Post-traitement — {len(all_fixes)} correction(s) automatique(s) :")
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

    # ── Couche 1 : Analyse de la description ──────────────────────────────────

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
CONTEXTE — Infrastructure déjà déployée dans ce projet :
{files_summary}

Ne recrée pas ces ressources. Réutilise leurs noms/IDs si nécessaire.
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
      "parameters": {{"vm_size": "Standard_B2s", "os": "ubuntu-22.04"}}
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

    # ── Couche 1 : Génération du code Terraform ────────────────────────────────

    def generate_terraform(
        self,
        analysis: InfraAnalysis,
        existing_tf: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """
        Génère les fichiers Terraform en 3 couches :
          1. LLM génère le code
          2. Post-traitement Python (corrections déterministes)
          3. Second LLM de validation (dépendances, références)
        """
        resources_desc = json.dumps(
            [{"type": r.type, "name": r.name, "parameters": r.parameters}
             for r in analysis.resources],
            indent=2,
        )

        if existing_tf:
            files_summary = "\n\n".join(
                f"### {fname}\n```hcl\n{content}\n```"
                for fname, content in existing_tf.items()
            )
            existing_context = f"""
PROJET TERRAFORM EXISTANT — lis TOUT le code ci-dessous avant de générer quoi que ce soit :

{files_summary}

RÈGLES :
1. Intègre les nouvelles ressources DIRECTEMENT dans les fichiers existants (main.tf, variables.tf, outputs.tf).
2. Retourne chaque fichier MODIFIÉ avec son contenu COMPLET (ancien + nouveau).
3. Ne crée pas de nouveau fichier sauf si c'est un module entièrement nouveau.
4. Réutilise les variables existantes sans les redéclarer.
5. Ne régénère PAS providers.tf s'il existe déjà.
"""
        else:
            existing_context = """
Génère un projet Terraform complet avec : providers.tf, variables.tf, main.tf, outputs.tf
Ne génère PAS de bloc backend dans providers.tf.
"""

        tfvars_values = (
            f'naming_prefix = "{analysis.naming_prefix}"\n'
            f'location      = "{analysis.location}"\n'
            f'environment   = "{analysis.environment}"\n'
        )

        prompt = f"""
{'Modifie le projet Terraform existant' if existing_tf else 'Crée un nouveau projet Terraform Azure'} pour provisionner les ressources suivantes.
{existing_context}
Projet      : {analysis.project_name}
Environnement: {analysis.environment}
Région      : {analysis.location}
Préfixe     : {analysis.naming_prefix}
Tags        : {json.dumps(analysis.tags)}
Ressources  : {resources_desc}

Retourne un JSON {{nom_fichier: contenu_hcl}} contenant aussi terraform.tfvars avec :
{tfvars_values}
"""

        # ── Couche 1 : génération LLM ──────────────────────────────────────────
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
        files: dict[str, str] = json.loads(response.choices[0].message.content)

        # ── Couche 2 : post-traitement déterministe ────────────────────────────
        files = _post_process(files)

        # ── Couche 3 : validation LLM (dépendances et références) ─────────────
        files = self._validate_and_correct(files)

        # README automatique
        files["README.md"] = self._generate_readme(analysis, list(files.keys()))

        return files

    # ── Couche 3 : Validation et correction par le LLM ────────────────────────

    def _validate_and_correct(self, files: dict[str, str]) -> dict[str, str]:
        """
        Second appel LLM : vérifie les dépendances Terraform et corrige
        les références en dur, ressources manquantes, etc.
        Retourne les fichiers avec les corrections appliquées.
        """
        tf_content = "\n\n".join(
            f"### {fname}\n```hcl\n{content}\n```"
            for fname, content in files.items()
            if fname.endswith(".tf")
        )

        if not tf_content.strip():
            return files

        prompt = f"""
Voici du code Terraform Azure généré automatiquement. Vérifie et corrige les problèmes.

{tf_content}

Vérifie OBLIGATOIREMENT ces points et CORRIGE tout ce qui est incorrect :

1. DÉPENDANCES MANQUANTES
   - Si azurerm_subnet existe → azurerm_virtual_network doit exister dans le même code
   - Si azurerm_virtual_network existe → azurerm_resource_group doit exister dans le même code
   - Si azurerm_storage_account existe → azurerm_resource_group doit exister

2. RÉFÉRENCES EN DUR INTERDITES
   - virtual_network_name = "nom-en-dur" → remplacer par azurerm_virtual_network.XXXX.name
   - resource_group_name = "nom-en-dur" → remplacer par azurerm_resource_group.XXXX.name
   - Tout attribut qui référence une autre ressource Azure doit utiliser une référence Terraform

3. ATTRIBUTS INVALIDES À SUPPRIMER
   - azurerm_subnet : supprimer tags, private_endpoint_network_policies_enabled,
     enforce_private_link_endpoint_network_policies, enforce_private_link_service_network_policies
   - azurerm_network_security_rule, azurerm_route, azurerm_role_assignment : supprimer tags
   - azurerm_virtual_network_peering, azurerm_subnet_network_security_group_association : supprimer tags

4. COMPLETUDE
   - Toutes les variables utilisées (var.X) doivent être déclarées dans variables.tf avec un default

Retourne un JSON {{nom_fichier: contenu_complet_corrigé}} avec UNIQUEMENT les fichiers qui ont été modifiés.
Si un fichier est correct, ne l'inclus PAS dans la réponse.
Si tous les fichiers sont corrects, retourne {{}}.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": "Tu es un expert Terraform. Valide et corrige le code fourni. Réponds UNIQUEMENT en JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=8000,
                response_format={"type": "json_object"},
            )

            corrections: dict[str, str] = json.loads(response.choices[0].message.content)

            if corrections:
                print(f"\n  ✅ Validation LLM — {len(corrections)} fichier(s) corrigé(s) :")
                for fname in corrections:
                    print(f"     • {fname}")
                # Appliquer les corrections (uniquement les fichiers .tf et .tfvars)
                for fname, content in corrections.items():
                    if fname.endswith((".tf", ".tfvars")):
                        files[fname] = content
            else:
                print("\n  ✅ Validation LLM — aucune correction nécessaire.")

        except Exception as e:
            print(f"\n  ⚠️  Validation LLM ignorée (erreur) : {e}")

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
terraform init
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

## Fichiers

{chr(10).join(f'- `{f}`' for f in tf_files)}

## Tags

```json
{json.dumps(analysis.tags, indent=2)}
```
"""
