"""
main.py — Point d'entrée de l'Agent IA DevOps
Orchestre : Jira (To Do) → In Progress → Analyse → Terraform → GitHub → Plan → Validation → Done
"""

import os
import sys
from datetime import datetime

_CI = os.getenv("AGENT_CI_MODE", "false").lower() in ("true", "1")
_SKIP_VAL = os.getenv("AGENT_SKIP_VALIDATION", "false").lower() in ("true", "1")
_AUTO_MERGE = os.getenv("AGENT_AUTO_MERGE", "false").lower() in ("true", "1")
_FORCED_TICKET = os.getenv("AGENT_TICKET", "").strip()

from agent.config import load_config
from agent.openai_client import OpenAIClient
from agent.github_manager import GitHubManager
from agent.jira_manager import JiraManager


# ── Helpers d'affichage ──────────────────────────────────────────────────────

def banner(text: str) -> None:
    width = 60
    print("\n" + "═" * width)
    print(f"  {text}")
    print("═" * width)


def section(text: str) -> None:
    print(f"\n▶  {text}")
    print("─" * 50)


def success(text: str) -> None:
    print(f"  ✅  {text}")


def info(text: str) -> None:
    print(f"  ℹ  {text}")


def warn(text: str) -> None:
    print(f"  ⚠️  {text}")


def ask_confirmation(prompt: str, ci_default: bool = True) -> bool:
    """Demande une confirmation oui/non à l'opérateur.

    En mode CI (AGENT_CI_MODE=true), répond automatiquement avec ci_default.
    ci_default=False pour les confirmations où l'échec doit stopper le pipeline.
    """
    if _CI:
        answer = "oui" if ci_default else "non"
        info(f"[CI] {prompt} → {answer} (automatique)")
        return ci_default
    while True:
        answer = input(f"\n  {prompt} [oui/non] : ").strip().lower()
        if answer in ("oui", "o", "yes", "y"):
            return True
        if answer in ("non", "n", "no"):
            return False
        print("  → Répondez 'oui' ou 'non'.")


# ── Agent principal ──────────────────────────────────────────────────────────

def run_agent() -> None:
    banner("Agent IA DevOps — Provisioning Terraform Automatisé")
    print("  Source des tâches : tickets Jira (To Do → In Progress → Done)")
    print("  Cible GitHub      : infrastructure provisionnée automatiquement.\n")

    # ── 0. Configuration ─────────────────────────────────────────────────────
    section("0. Chargement de la configuration")
    try:
        config = load_config()
        success("Configuration chargée avec succès.")
        info(f"Azure OpenAI : {config.azure_openai_endpoint}")
        info(f"GitHub       : {config.github_owner} / {config.github_infra_repo}")
        info(f"Jira         : {config.jira_url}  |  projet : {config.jira_project_key}")
    except EnvironmentError as e:
        print(f"\n  ❌ Erreur de configuration :\n{e}")
        sys.exit(1)

    jira = JiraManager(config)

    # ── 1. Lecture des tickets Jira (To Do) ──────────────────────────────────
    section("1. Récupération des tickets Jira en 'To Do'")
    try:
        tickets = jira.get_todo_tickets()
    except Exception as e:
        print(f"  ❌ Impossible de contacter Jira : {e}")
        sys.exit(1)

    if not tickets:
        print("  ℹ  Aucun ticket 'To Do' trouvé dans le projet "
              f"'{config.jira_project_key}'. Arrêt.")
        sys.exit(0)

    print(f"\n  {len(tickets)} ticket(s) disponible(s) :\n")
    for i, t in enumerate(tickets, 1):
        fields = t["fields"]
        priority = (fields.get("priority") or {}).get("name", "—")
        print(f"  [{i}] {t['key']:12s}  [{priority:8s}]  {fields['summary']}")

    # Sélection du ticket
    if _CI:
        if _FORCED_TICKET:
            matched = [t for t in tickets if t["key"] == _FORCED_TICKET]
            if matched:
                selected_ticket = matched[0]
            else:
                warn(f"[CI] Ticket '{_FORCED_TICKET}' non trouvé — utilisation du premier ticket")
                selected_ticket = tickets[0]
        else:
            selected_ticket = tickets[0]
        info(f"[CI] Ticket sélectionné automatiquement : {selected_ticket['key']}")
    else:
        print()
        while True:
            raw = input(f"  Choisissez un ticket [1-{len(tickets)}] (Entrée = 1) : ").strip()
            if raw == "":
                selected_ticket = tickets[0]
                break
            if raw.isdigit() and 1 <= int(raw) <= len(tickets):
                selected_ticket = tickets[int(raw) - 1]
                break
            print("  → Choix invalide.")
    issue_key     = selected_ticket["key"]
    issue_summary = selected_ticket["fields"]["summary"]

    success(f"Ticket sélectionné : {issue_key} — {issue_summary}")

    # ── 2. Transition → In Progress ──────────────────────────────────────────
    section(f"2. Transition Jira : {issue_key} → In Progress")
    if jira.transition_to_in_progress(issue_key):
        success(f"{issue_key} passé en 'In Progress'.")
        jira.add_comment(
            issue_key,
            f"🤖 L'Agent IA DevOps a pris en charge ce ticket ({datetime.now().strftime('%Y-%m-%d %H:%M')}). "
            "Provisioning Terraform en cours."
        )
    else:
        warn(f"Impossible de transitionner {issue_key}. Continuons quand même.")

    # ── 3. Lecture de la description du ticket ───────────────────────────────
    section("3. Lecture de la description du ticket Jira")
    description = jira.get_description(selected_ticket)

    if not description:
        print("  ❌ Description vide dans le ticket Jira. Arrêt.")
        jira.transition_to_todo(issue_key)
        sys.exit(1)

    print(f"\n  📋 Description extraite du ticket {issue_key} :\n")
    for line in description.splitlines()[:15]:
        print(f"     {line}")
    if len(description.splitlines()) > 15:
        print("     ...")

    if not ask_confirmation("Utiliser cette description pour générer l'infrastructure ?"):
        print("  → Arrêt demandé. Le ticket est remis en 'To Do'.")
        jira.transition_to_todo(issue_key)
        sys.exit(0)

    # ── 4. Lecture du projet infra-provisioned + Analyse par Azure OpenAI ───────
    section("4. Lecture du projet existant + Analyse par Azure OpenAI")
    print("  Lecture du repo infra-provisioned en cours...")

    openai_client = OpenAIClient(config)
    gh_early = GitHubManager(config)

    existing_tf: dict = {}
    try:
        gh_early.ensure_repo_exists()
        gh_early.setup_infra_repo()
        existing_tf = gh_early.get_repo_context()
        if existing_tf:
            info(f"Projet existant détecté : {len(existing_tf)} fichier(s) .tf trouvé(s).")
            for fname in existing_tf:
                print(f"     • {fname}")
        else:
            info("Aucun fichier .tf existant — génération complète du projet.")

        analysis = openai_client.analyze_description(description, existing_tf=existing_tf)
    except Exception as e:
        print(f"  ❌ Erreur : {e}")
        jira.transition_to_todo(issue_key)
        sys.exit(1)

    print(f"\n  📋 Résumé de l'analyse :")
    print(f"     Projet       : {analysis.project_name}")
    print(f"     Environnement: {analysis.environment}")
    print(f"     Région       : {analysis.location}")
    print(f"     Ressources   :")
    for r in analysis.resources:
        params = ", ".join(f"{k}={v}" for k, v in r.parameters.items())
        print(f"       • {r.type.upper()} '{r.name}'" + (f" ({params})" if params else ""))

    print(f"\n  → {analysis.summary}\n")

    if not ask_confirmation("Cette analyse est-elle correcte ? Continuer ?"):
        print("  → Arrêt demandé. Le ticket est remis en 'To Do'.")
        jira.transition_to_todo(issue_key)
        sys.exit(0)

    # ── 5. Génération du code Terraform ──────────────────────────────────────
    section("5. Génération du code Terraform")
    print("  Génération des fichiers .tf selon les bonnes pratiques Azure...")

    try:
        tf_files = openai_client.generate_terraform(
            analysis, existing_tf=existing_tf, issue_key=issue_key
        )
    except Exception as e:
        print(f"  ❌ Erreur génération Terraform : {e}")
        sys.exit(1)

    success(f"{len(tf_files)} fichier(s) Terraform (modifications) :")
    for fname in tf_files:
        print(f"     • {fname}")

    if "main.tf" in tf_files:
        print("\n  ── Aperçu main.tf (10 premières lignes) ──")
        for line in tf_files["main.tf"].split("\n")[:10]:
            print(f"    {line}")
        print("    ...")

    # ── 6. Préparation du repository GitHub ──────────────────────────────────
    section("6. Préparation du repository GitHub")

    gh = gh_early
    try:
        repo_url = gh.ensure_repo_exists()
        success(f"Repo : {repo_url}")
        if gh.ensure_standard_pipeline():
            success("Pipeline terraform-standard.yml installé/mis à jour.")
        else:
            info("Pipeline terraform-standard.yml déjà à jour.")
        if gh.bootstrap_infra_repo():
            success(f"Bootstrap {config.github_infra_repo} (dossier terraform/) créé.")
        else:
            info("Bootstrap terraform/ déjà présent.")
    except Exception as e:
        print(f"  ❌ Erreur GitHub : {e}")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    branch_name = f"feature/{issue_key}-{analysis.project_name}-{analysis.environment}-{timestamp}"
    info(f"Branche : {branch_name}")

    try:
        gh.create_branch(branch_name)
    except Exception as e:
        print(f"  ❌ Impossible de créer la branche : {e}")
        sys.exit(1)

    # ── 7. Push des fichiers Terraform sur GitHub ─────────────────────────────
    section("7. Push des fichiers Terraform sur GitHub")

    commit_msg = f"feat({issue_key}): provision {analysis.project_name} — {analysis.environment}"
    try:
        pushed_paths = gh.push_files(
            branch=branch_name,
            files=tf_files,
            commit_message=commit_msg,
            issue_key=issue_key,
        )
    except Exception as e:
        print(f"  ❌ Erreur push : {e}")
        sys.exit(1)

    success(f"{len(pushed_paths)} fichier(s) modifié(s) sur la branche {branch_name} :")
    for p in pushed_paths:
        print(f"     • {p}")
    info("Modifications dans le projet existant — merge PR → terraform apply sur infra-provisioned.")

    # ── 8. Création de la Pull Request ───────────────────────────────────────
    section("8. Création de la Pull Request")

    resources_md = "\n".join(
        f"| `{r.type}` | `{r.name}` | {', '.join(f'`{k}={v}`' for k, v in r.parameters.items())} |"
        for r in analysis.resources
    )

    pr_body = f"""
## 🤖 Infrastructure générée par l'Agent IA DevOps

**Ticket Jira :** [{issue_key}]({config.jira_url}/browse/{issue_key}) — {issue_summary}

**Description originale :**
> {description[:500]}{'...' if len(description) > 500 else ''}

**Analyse :**
{analysis.summary}

### Ressources Azure à créer

| Type | Nom | Paramètres |
|------|-----|------------|
{resources_md}

### Paramètres

- **Région :** `{analysis.location}`
- **Environnement :** `{analysis.environment}`
- **Préfixe :** `{analysis.naming_prefix}`

---

> ⚠️ **Action requise** : Reviewer le `terraform plan` dans les checks CI/CD
> avant d'approuver cette PR. Le `terraform apply` sera déclenché automatiquement
> après le merge sur `main`.
"""

    try:
        pr = gh.create_pull_request(
            branch=branch_name,
            analysis=analysis,
            pr_body=pr_body,
        )
        pr_number = pr["number"]
        pr_url = pr["html_url"]
    except Exception as e:
        print(f"  ❌ Erreur création PR : {e}")
        sys.exit(1)

    # Lier la PR au ticket Jira
    jira.add_comment(
        issue_key,
        f"🔗 Pull Request créée : {pr_url}\n"
        f"Branche : {branch_name}\n"
        f"Ressources : {len(analysis.resources)} ressource(s) Azure à provisionner."
    )

    # En mode CI sans skip_validation : sortie immédiate après PR, pas d'attente plan.
    if _CI and not _SKIP_VAL:
        banner("CI — PR prête, validation humaine requise")
        print(f"""
  ✅ PR #{pr_number} créée avec succès.

  🔗 Pull Request  : {pr_url}
  🎫 Ticket Jira   : {config.jira_url}/browse/{issue_key}
  📋 Ressources    : {len(analysis.resources)} ressource(s) Azure

  Reviewez le Terraform Plan dans les checks GitHub Actions,
  puis mergez la PR pour déclencher le terraform apply.
  Le ticket {issue_key} reste en 'In Progress' jusqu'au merge.
        """)
        sys.exit(0)

   
    # ── 9. Surveillance du pipeline GitHub Actions ────────────────────────────
    section("9. Surveillance du pipeline GitHub Actions (Terraform Plan)")
    info(f"PR #{pr_number} : {pr_url}")
    info("Le pipeline exécute : init → fmt → validate → plan")

    # ✅ Fix : valeur par défaut pour éviter NameError
    conclusion = "unknown"

    completed_run = gh.wait_for_plan_completion(pr_number=pr_number, timeout_minutes=15)

    if completed_run:
        run_id = completed_run["id"]
        conclusion = completed_run.get("conclusion", "unknown")
        run_url = completed_run.get("html_url", "")

        print(f"\n  Pipeline terminé → {conclusion.upper()}")
        info(f"Voir les détails : {run_url}")

        print("\n  ── Résumé du Terraform Plan ──")
        plan_output = gh.get_plan_output(run_id)
        if plan_output:
            for line in plan_output.split("\n")[:30]:
                print(f"    {line}")

        if conclusion != "success":
            warn("Le pipeline a échoué. Vérifiez les logs sur GitHub Actions.")
    else:
        # ✅ Fix : timeout → ne pas crasher, demander à l'humain
        warn("Timeout : résultats du plan non disponibles dans le délai imparti.")
        info(f"Vérifiez manuellement : {pr_url}")
        warn("Le plan n'a pas pu être vérifié automatiquement.")



        

    # ── 10. Validation avant merge ───────────────────────────────────────────
    auto_merge = _AUTO_MERGE or (
        _SKIP_VAL and (_CI or os.getenv("AGENT_AUTO_VALIDATE_PLAN", "").lower() in ("true", "1"))
    )
    plan_ok = conclusion in ("success", "unknown")

    if auto_merge and plan_ok:
        approved = True
        info("[Autonome] Merge et apply approuvés automatiquement.")
    else:
        banner("⛔  VALIDATION HUMAINE REQUISE — Terraform Apply")
        print(f"""
  Avant de procéder au déploiement, vérifiez :

  1. 👀 Résultats du plan ci-dessus (conclusion : {conclusion.upper()})
  2. 🎫 Ticket Jira    : {config.jira_url}/browse/{issue_key}
  3. 🔗 Pull Request   : {pr_url}
  4. 📋 Ressources     : {len(analysis.resources)} ressource(s) Azure à créer

  ⚠  Le merge déclenchera terraform apply sur infra-provisioned (dossier terraform/).
""")
        approved = ask_confirmation("Approuvez-vous le merge et le déploiement ?", ci_default=False)

    # ── 11. Merge ou Refus ───────────────────────────────────────────────────
    if approved:
        section("11. Merge de la PR → Déclenchement de Terraform Apply")
        print("  Merge en cours sur main...")

        try:
            merge_sha = gh.merge_pull_request(pr_number, analysis.project_name)
            success("PR mergée avec succès.")
            info("Le job 'Terraform Apply' démarre sur infra-provisioned.")
            actions_url = f"https://github.com/{config.github_owner}/{config.github_infra_repo}/actions"
            info(f"Suivez : {actions_url}")

            wait_apply = os.getenv("WAIT_FOR_APPLY_COMPLETION", "true").lower() in ("true", "1")
            apply_run = None
            if wait_apply:
                section("11b. Attente fin Terraform Apply")
                info("Attente du workflow Apply (max 25 min)...")
                apply_run = gh.wait_for_apply_completion(branch="main", timeout_minutes=25)
                if apply_run:
                    ac = apply_run.get("conclusion", "unknown")
                    info(f"Apply terminé : {ac.upper()} — {apply_run.get('html_url', '')}")
                    if ac != "success":
                        warn("Apply en échec — vérifiez les logs GitHub Actions.")
                else:
                    warn("Timeout apply — vérifiez manuellement GitHub Actions.")

            # ── Transition Jira → Done ────────────────────────────────────
            section(f"12. Transition Jira : {issue_key} → Done")
            apply_ok = apply_run is None or apply_run.get("conclusion") == "success"
            if apply_ok and jira.transition_to_done(issue_key):
                success(f"Ticket {issue_key} passé en 'Done'.")
            elif not apply_ok:
                warn(f"Apply non confirmé — ticket {issue_key} laissé en In Progress.")
            else:
                warn(f"Impossible de transitionner {issue_key} en 'Done'. Faites-le manuellement.")

            status_msg = "déployée" if apply_ok else "PR mergée, apply à vérifier"
            jira.add_comment(
                issue_key,
                f"✅ Infrastructure {status_msg}.\n"
                f"PR : {pr_url}\n"
                f"SHA : {merge_sha[:8]}\n"
                f"Repo : {config.github_infra_repo}\n"
                f"Actions : {actions_url}"
            )

            print(f"""
  ┌──────────────────────────────────────────────────────┐
  │  🚀 Déploiement lancé !                              │
  │                                                      │
  │  Ticket Jira  : {issue_key:<37}│
  │  Projet       : {analysis.project_name:<37}│
  │  Environnement: {analysis.environment:<37}│
  │  SHA merge    : {merge_sha[:8]:<37}│
  │  Statut Jira  : Done ✅                              │
  │                                                      │
  │  GitHub Actions → terraform apply en cours...        │
  └──────────────────────────────────────────────────────┘
""")
        except Exception as e:
            print(f"  ❌ Erreur lors du merge : {e}")
            sys.exit(1)

    else:
        section("11. Déploiement refusé")
        reason = "[CI] Refus automatique" if _CI else input("  Raison du refus (optionnel) : ").strip()

        try:
            gh.close_pull_request(pr_number)
        except Exception:
            pass

        # Remettre le ticket en To Do
        jira.transition_to_todo(issue_key)
        jira.add_comment(
            issue_key,
            f"❌ Déploiement refusé par l'opérateur.\n"
            + (f"Raison : {reason}\n" if reason else "")
            + "Ticket remis en 'To Do' pour retraitement."
        )

        print(f"""
  ❌ Déploiement refusé par l'opérateur.
  {f'Raison : {reason}' if reason else ''}

  Ticket Jira  : {issue_key} → remis en 'To Do'
  PR #{pr_number}   : fermée
  Branche '{branch_name}' conservée pour corrections manuelles.
""")


# ── Point d'entrée ───────────────────────────────────────────────────────────

def main():
    try:
        run_agent()
    except KeyboardInterrupt:
        print("\n\n  → Interrompu par l'utilisateur. Arrêt propre.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ❌ Erreur inattendue : {e}")
        raise


if __name__ == "__main__":
    main()
