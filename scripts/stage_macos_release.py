from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

REPOSITORY = "feifeigong/ai-first-tools"
CODEX_IMPORT_CHECKS = {
    'foreign_reasoning_is_lossless_history_not_provider_state',
    'hosted_and_compaction_payloads_are_archived_not_replayed',
    'complete_tool_pairs_and_identifier_protection_are_preserved',
    'old_import_can_be_copied_once_and_new_import_still_deduplicates',
    'unknown_or_malformed_history_is_still_rejected',
    'normal_cursor_import_and_two_saved_followups_round_trip',
    'compressed_project_history_listing_export_and_truncation_guard',
}
REFRESH_CHECKS = {'nativeDraftPreserved','nativeEmptyComposerRecognized','nativeBusyPreserved',
                  'explicitNativeReloadExecuted','actualWebKitDocumentReloaded','sameApplicationKeptRunning'}


def validated_assets(directory: Path, release: str, *, local_preview: bool = False) -> list[Path]:
    if not re.fullmatch(r"\d+\.\d+\.\d+-macos-preview\.\d+", release):
        raise ValueError("Invalid Mac preview version")
    assets = []
    sums = []
    for architecture in ("arm64", "x86_64"):
        source = directory / f"macos-{architecture}"
        suffix = '-local-parity' if local_preview else ''
        name = f"AI-First-Tools-{release}{suffix}-macos-{architecture}.dmg"
        dmg = source / name
        with dmg.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        expected = f"{digest}  {name}"
        if (source / f"SHA256SUMS-{architecture}.txt").read_text().strip() != expected:
            raise ValueError("DMG digest mismatch")
        number = int(release.rsplit('.',1)[1])
        kinds = ("self", "smoke", "network", "update", 'resume') if number >= 15 else ("self", "smoke", "network", "update")
        if number >= 19: kinds += ('memory', 'reset', 'reset-rules', 'codex-import', 'copilot-refresh')
        for kind in kinds:
            report = source / f"{kind}-test.json"
            result = json.loads(report.read_text())
            if result.get("passed") is not True or not result.get("checks") or not all(value is True for value in result["checks"].values()):
                raise ValueError("Native app checks did not pass")
            if kind == 'self' and ((result.get('version',{}).get('developmentPreview') is True) != local_preview
                    or local_preview and result['checks'].get('developmentPreviewIsolation') is not True):
                raise ValueError('Development preview and formal application identities must not be mixed')
            if kind == 'self' and number >= 21 and (not {'localizedProductName','finderDisplayName','nativeProcessName'} <= set(result['checks']) or result.get('finderScope') != 'product'):
                raise ValueError('The renamed product must be verified through native localized and Finder names')
            if kind == "update" and not {"nativeUpdateClick", "bridgeDrained", "nativeParentExit"}.issubset(result["checks"]):
                raise ValueError("Native update click and bridge handoff checks are required")
            if kind == 'resume' and not {'nativeRuntimeWithoutExternalInstallation','singlePackagedWatcher','startupSwitchIndependent','stopBlocksStartupRelaunch','updateRestoresRunningAndStartup','realLaunchAgentStopsWithoutRelaunch','finderRemovalCleansBackgroundAndStartup','cleanupPreservesUserSettings'} <= set(result['checks']):
                raise ValueError('Actual bundled auto-resume lifecycle checks are required')
            if kind=='smoke' and int(release.rsplit('.',1)[1])>=15 and result['checks'].get('autoResumeControlBridge') is not True:
                raise ValueError('Native auto-resume page and bridge check is required')
            if kind == 'smoke' and number >= 19 and not {'resetCalendarBridge','independentReminderSwitch'} <= set(result['checks']):
                raise ValueError('Native reset calendar and independent switch checks are required')
            if number >= 22 and (kind == 'self' and result['checks'].get('bundledReleaseHighlights') is not True
                    or kind == 'smoke' and not {'nativeReleaseHighlightsDialog','releaseHighlightsAcknowledgement'} <= set(result['checks'])):
                raise ValueError('Bundled release highlights, native dialog and acknowledgement checks are required')
            if number >= 24 and kind == 'self' and result['checks'].get('weeklyCreditRequiresExhaustion') is not True:
                raise ValueError('Packaged weekly credit boundary check is required')
            if kind == 'memory' and not {'database_scope_guard','original_archive','bundled_stdio_mcp_handshake','discarded_legacy_entry_no_longer_blocks_move','source_badge_uses_current_entry','current_schema_rollback_preserves_legacy_orphan'} <= set(result['checks']):
                raise ValueError('Native complete archive, read-only memory and repeat-move checks are required')
            if kind == 'reset' and not {'frozenSharedRuleBridgeAndSwitch','independentAfterLauncherExit','singleOwnedNotifier','nativeWindowClosePreservesNotifier','nativeChinesePopupHasNoAutomaticResumeAction','anotherPackageCannotStopNotifier','cooperativeUpdateRestoresNotifier','stopPreservesPreferences'} <= set(result['checks']):
                raise ValueError('Native reset notification lifecycle checks are required')
            if kind == 'reset-rules' and (len(result['checks']) < 20 or set(result.get('sharedWindowsSources',{})) != {'ResetNewsService.cs','ResetNewsDiscovery.cs','ResetNewsPresentation.cs','ResetCalendarModel.cs'}):
                raise ValueError('Actual shared Windows reset rule checks are required')
            if kind == 'codex-import' and (not CODEX_IMPORT_CHECKS <= set(result['checks'])
                    or result.get('modelRequests') != 0 or result.get('nativeContinuationVerified') is not False
                    or result.get('host') != 'Darwin' or result.get('frozen') is not True):
                raise ValueError('Packaged Mac history compatibility and compressed export checks are required')
            if kind == 'copilot-refresh' and (not REFRESH_CHECKS <= set(result['checks'])
                    or result.get('modelRequests') != 0 or result.get('host') != 'Darwin' or result.get('frozen') is not True):
                raise ValueError('Actual Mac draft, busy and explicitly labelled native reload guards are required')
            if kind != "smoke" and (result.get("architecture") != architecture or result.get("version", {}).get("release") != release):
                raise ValueError("Native report version or architecture mismatch")
            target = directory / f"{kind}-test-{architecture}.json"
            shutil.copy2(report, target)
            assets.append(target)
        target = directory / name
        shutil.copy2(dmg, target)
        assets.append(target)
        sums.append(expected)
    manifest = directory / "SHA256SUMS.txt"
    manifest.write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    return [*assets, manifest]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    arguments = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", arguments.commit):
        parser.error("Expected a full build commit")
    root = Path(__file__).resolve().parent.parent
    release = json.loads((root / "macos/version.json").read_text())["release"]
    tag = f"v{release}"
    command = ["gh", "api", f"repos/{REPOSITORY}/releases?per_page=100"]
    response = subprocess.run(command, capture_output=True, text=True, check=True)
    releases = json.loads(response.stdout)
    if not isinstance(releases, list):
        raise ValueError("Invalid release list")
    draft = next((release for release in releases if release.get("tag_name") == tag), None)
    if draft is None or draft.get("draft") is not True:
        print("No matching draft; published releases left unchanged")
        return
    reference = json.loads(subprocess.run(["gh", "api", f"repos/{REPOSITORY}/git/ref/tags/{tag}"], check=True, capture_output=True, text=True).stdout)
    if reference.get("object", {}).get("type") != "commit" or reference["object"]["sha"] != arguments.commit:
        raise ValueError("Prepare a lightweight release tag at the verified build commit")
    assets = validated_assets(arguments.artifacts, release)
    subprocess.run(["gh", "release", "upload", tag, "--repo", REPOSITORY, "--clobber", *map(str, assets)], check=True)
    print("Validated assets staged; release remains a draft")


if __name__ == "__main__":
    main()
