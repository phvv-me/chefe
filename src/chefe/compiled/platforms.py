from typing import Self

from ..base import Model, Toml
from ..manifest import Manifest


class PlatformMatrix(Model):
    """Pixi platform descriptors and the feature routes that select them."""

    workspace: list[Toml]
    environments: dict[str, list[str]]
    default: list[str]

    @classmethod
    def from_manifest(cls, manifest: Manifest) -> Self:
        """Expand Chefe virtual package floors into named Pixi platform variants."""
        platforms = manifest.workspace.platforms
        root_names = {
            platform: f"{platform}-system" if manifest.system else platform
            for platform in platforms
        }
        workspace: list[Toml] = [
            {"name": root_names[platform], "platform": platform, **manifest.system}
            if manifest.system
            else platform
            for platform in platforms
        ]
        requires_routing = bool(
            manifest.system or any(env.system for env in manifest.envs.values())
        )
        environments: dict[str, list[str]] = {}
        for name, env in manifest.envs.items():
            selected = env.platforms or platforms
            if env.system and env.system != manifest.system:
                names = [f"{platform}-{name}" for platform in selected]
                workspace.extend(
                    {"name": variant, "platform": platform, **env.system}
                    for platform, variant in zip(selected, names, strict=True)
                )
            else:
                names = [root_names[platform] for platform in selected]
            if env.platforms or requires_routing:
                environments[name] = names
        default = list(root_names.values()) if requires_routing else []
        return cls(workspace=workspace, environments=environments, default=default)
