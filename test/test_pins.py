import json

from juliapkg.deps import (
    PkgSpec,
    _install_script,
    _pins_from_manifest,
    find_pins,
)

EXAMPLE_UUID = "7876af07-990d-54b4-ab0e-23690620f79a"
CRAYONS_UUID = "a8cc5b0e-0ffa-5ad4-8c14-923d3ee1735f"


def test_pins_from_manifest():
    manifest = {
        "julia_version": "1.11.0",
        "manifest_format": "2.0",
        "project_hash": "abc",
        "deps": {
            "Example": [
                {
                    "uuid": EXAMPLE_UUID,
                    "version": "0.5.4",
                    "git-tree-sha1": "11820aa9c229fd3833d4bd69e5e75ef4e7273bf1",
                }
            ],
            # stdlib: no git-tree-sha1, not pinnable
            "LinearAlgebra": [
                {"uuid": "37e2e46d-f89d-539d-b4ee-838fcccc9c8e", "version": "1.11.0"}
            ],
            # dev/path package: pinned by its source already
            "MyLocalPkg": [
                {
                    "uuid": "123e4567-e89b-12d3-a456-426614174000",
                    "version": "0.1.0",
                    "git-tree-sha1": "0000000000000000000000000000000000000000",
                    "path": "/some/where",
                }
            ],
            # two packages with the same name: ambiguous, skipped
            "Dup": [
                {"uuid": "123e4567-e89b-12d3-a456-426614174001", "version": "1.0.0"},
                {"uuid": "123e4567-e89b-12d3-a456-426614174002", "version": "2.0.0"},
            ],
        },
    }
    pins = _pins_from_manifest(manifest)
    assert pins == {"Example": {"uuid": EXAMPLE_UUID, "version": "0.5.4"}}


def test_pins_from_manifest_format_1():
    manifest = {
        "Example": [
            {
                "uuid": EXAMPLE_UUID,
                "version": "0.5.4",
                "git-tree-sha1": "11820aa9c229fd3833d4bd69e5e75ef4e7273bf1",
            }
        ],
    }
    pins = _pins_from_manifest(manifest)
    assert pins == {"Example": {"uuid": EXAMPLE_UUID, "version": "0.5.4"}}


def test_find_pins(tmp_path):
    fn1 = tmp_path / "a" / "juliapkg.pinned.json"
    fn2 = tmp_path / "b" / "juliapkg.pinned.json"
    fn1.parent.mkdir()
    fn2.parent.mkdir()
    fn1.write_text(
        json.dumps(
            {
                "packages": {
                    "Example": {"uuid": EXAMPLE_UUID, "version": "0.5.4"},
                    "DevPkg": {
                        "uuid": "123e4567-e89b-12d3-a456-426614174000",
                        "version": "0.1.0",
                    },
                }
            }
        )
    )
    fn2.write_text(
        json.dumps(
            {
                "packages": {
                    "Example": {"uuid": EXAMPLE_UUID, "version": "0.5.5"},
                    "Crayons": {"uuid": CRAYONS_UUID, "version": "4.1.1"},
                }
            }
        )
    )
    pkgs = [
        PkgSpec(
            name="DevPkg",
            uuid="123e4567-e89b-12d3-a456-426614174000",
            path="/some/where",
        )
    ]
    pins = find_pins(pkgs, files=[str(fn2), str(fn1)])
    # files are processed in sorted order, so fn1 wins the Example conflict
    assert pins["Example"]["version"] == "0.5.4"
    assert pins["Crayons"]["version"] == "4.1.1"
    # packages with a fixed source are not pinnable
    assert "DevPkg" not in pins


def test_install_script_no_pins():
    spec = PkgSpec(name="Example", uuid=EXAMPLE_UUID)
    script = _install_script([], [spec], {}, False, False)
    assert script == [
        "import Pkg",
        "Pkg.Registry.update()",
        "Pkg.add([",
        f'  Pkg.PackageSpec(name="Example", uuid="{EXAMPLE_UUID}"),',
        "])",
        "Pkg.resolve()",
        "Pkg.precompile()",
    ]


def test_install_script_pins():
    spec = PkgSpec(name="Example", uuid=EXAMPLE_UUID)
    pins = {
        "Example": {"uuid": EXAMPLE_UUID, "version": "0.5.4", "file": "x"},
        "Crayons": {"uuid": CRAYONS_UUID, "version": "4.1.1", "file": "x"},
    }
    script = _install_script([], [spec], pins, False, False)
    text = "\n".join(script)
    # pins are seeded before the real packages are added
    assert text.index("pins = Pkg.PackageSpec[") < text.index("Pkg.add([\n")
    assert (
        f'Pkg.PackageSpec(name="Example", uuid="{EXAMPLE_UUID}", version="0.5.4")'
        in text
    )
    # pin-only packages are removed from the project again
    assert 'pinonly = String["Crayons"]' in text
    assert "Pkg.rm(rmnames)" in text
    # relaxed pins produce a warning, not an error
    assert "@warn msg" in text
    assert "error(msg)" not in text


def test_install_script_pins_strict():
    spec = PkgSpec(name="Example", uuid=EXAMPLE_UUID)
    pins = {"Example": {"uuid": EXAMPLE_UUID, "version": "0.5.4", "file": "x"}}
    script = _install_script([], [spec], pins, True, False)
    text = "\n".join(script)
    assert "rethrow()" in text
    assert "error(msg)" in text
    assert "@warn msg" not in text
