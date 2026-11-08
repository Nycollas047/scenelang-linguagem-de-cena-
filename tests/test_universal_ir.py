from scenelang.universal_ir import UniversalScene, adapter_report, validate_ir


def test_universal_ir_validates_coordinate_geometry_and_unique_entities():
    ir = UniversalScene(entities=[{"id": "hero"}], geometry=[
        {"entity": "hero", "type": "box2", "coordinates": [0.1, 0.2, 0.3, 0.4]},
    ])
    assert validate_ir(ir) == []
    broken = ir.to_dict()
    broken["entities"].append({"id": "hero"})
    broken["geometry"][0]["coordinates"] = [0, 0, 0, 1]
    paths = {d["path"] for d in validate_ir(broken)}
    assert "$.entities" in paths and "$.geometry[0].coordinates" in paths


def test_ir_adapter_reports_explicit_losses():
    class GeometryOnly:
        name = "geometry-only"
        def capabilities(self): return {"entities", "geometry"}
        def export(self, scene): return None

    report = adapter_report(UniversalScene(), GeometryOnly())
    assert report.supported == ["entities", "geometry"]
    assert "temporal" in report.unsupported
    assert {x["feature"] for x in report.losses} == set(report.unsupported)


def test_scene_projection_keeps_existing_yaml_flow():
    from pathlib import Path
    from scenelang.validate import load_file

    _, scene, _ = load_file(Path(__file__).resolve().parents[1] / "examples" / "guardia.yaml")
    ir = scene.to_universal_ir()
    assert validate_ir(ir) == []
    assert len(ir.entities) == len(scene.entities)
    assert len(ir.geometry) == len(scene.entities)
    assert all(item["language"] == "scenelang.assert" for item in ir.constraints)
