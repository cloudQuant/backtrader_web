"""
Acceptance tests for Task 5: DAG Generator.

Validates Requirements: 3.1-3.8, 4.3
"""

import pytest

from app.services.orchestration.dag_generator import DAGGenerator


class TestDAGGeneratorSingleTask:
    """AT-3.1: Single task DAG generation."""

    def test_generate_single_dag_valid_python(self, tmp_path):
        """Generated DAG file is valid Python syntax."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        script = {
            "script_id": "stock_zh_a_hist",
            "source": "akshare",
            "timeout": 600,
            "description": "A股历史数据",
            "category": "stocks",
            "parameters": {"symbol": "000001"},
        }
        path = generator.generate_dag(script)
        assert path.endswith("dag_stock_zh_a_hist.py")
        # Verify valid Python
        content = open(path).read()
        compile(content, path, "exec")

    def test_generated_dag_contains_dag_id(self, tmp_path):
        """Generated file contains correct dag_id."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        script = {"script_id": "test_script", "source": "akshare", "timeout": 300, "category": "test"}
        path = generator.generate_dag(script)
        content = open(path).read()
        assert 'dag_id="dag_test_script"' in content

    def test_generated_dag_contains_python_operator(self, tmp_path):
        """Generated file uses PythonOperator."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        script = {"script_id": "my_script", "source": "akshare", "timeout": 300, "category": "test"}
        path = generator.generate_dag(script)
        content = open(path).read()
        assert "PythonOperator" in content

    def test_file_naming_convention(self, tmp_path):
        """File is named dag_{script_id}.py."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        script = {"script_id": "bond_zh_hs_daily", "source": "akshare", "timeout": 300, "category": "bonds"}
        path = generator.generate_dag(script)
        assert path.endswith("dag_bond_zh_hs_daily.py")


class TestDAGGeneratorWithTask:
    """AT-3.4, AT-3.5: default_args from task metadata."""

    def test_retries_from_task(self, tmp_path):
        """max_retries maps to retries in default_args."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        script = {"script_id": "test", "source": "akshare", "timeout": 600, "category": "test"}
        task = {"max_retries": 5, "schedule_expression": "0 8 * * *"}
        path = generator.generate_dag(script, task)
        content = open(path).read()
        assert '"retries": 5' in content

    def test_timeout_in_default_args(self, tmp_path):
        """timeout maps to execution_timeout."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        script = {"script_id": "test", "source": "akshare", "timeout": 900, "category": "test"}
        path = generator.generate_dag(script)
        content = open(path).read()
        assert "timedelta(seconds=900)" in content

    def test_schedule_interval_from_task(self, tmp_path):
        """schedule_expression converts to schedule_interval."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        script = {"script_id": "test", "source": "akshare", "timeout": 300, "category": "test"}
        task = {"max_retries": 3, "schedule_expression": "0 18 * * 1-5"}
        path = generator.generate_dag(script, task)
        content = open(path).read()
        assert "0 18 * * 1-5" in content


class TestDAGGeneratorScheduleConversion:
    """AT-3.4: Schedule expression conversion."""

    @pytest.mark.parametrize("input_expr,expected", [
        ("0 8 * * *", "0 8 * * *"),
        ("18:00", "00 18 * * *"),
        ("30m", "*/30 * * * *"),
        ("2h", "0 */2 * * *"),
        ("1d", "@daily"),
    ])
    def test_schedule_conversion(self, input_expr, expected):
        result = DAGGenerator._convert_schedule(input_expr)
        assert result == expected


class TestDAGGeneratorGrouped:
    """AT-3.6: Grouped DAG generation."""

    def test_grouped_dag_contains_all_tasks(self, tmp_path):
        """Grouped DAG has one task per script."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        scripts = [
            {"script_id": "task_a", "category": "stocks", "dependencies": []},
            {"script_id": "task_b", "category": "stocks", "dependencies": []},
            {"script_id": "task_c", "category": "stocks", "dependencies": []},
        ]
        path = generator.generate_grouped_dag(scripts, "stocks")
        content = open(path).read()
        assert "task_task_a" in content
        assert "task_task_b" in content
        assert "task_task_c" in content

    def test_grouped_dag_with_dependencies(self, tmp_path):
        """Dependencies generate >> operators."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        scripts = [
            {"script_id": "get_list", "category": "stocks", "dependencies": []},
            {"script_id": "get_hist", "category": "stocks", "dependencies": ["get_list"]},
        ]
        path = generator.generate_grouped_dag(scripts, "stocks")
        content = open(path).read()
        assert "task_get_list >> task_get_hist" in content


class TestDAGGeneratorDependencyValidation:
    """AT-3.3, AT-4.3: Cyclic dependency detection."""

    def test_no_cycle_returns_empty(self, tmp_path):
        """Acyclic graph returns no errors."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        scripts = [
            {"script_id": "a", "dependencies": []},
            {"script_id": "b", "dependencies": ["a"]},
            {"script_id": "c", "dependencies": ["b"]},
        ]
        errors = generator.validate_dependencies(scripts)
        assert errors == []

    def test_cycle_detected(self, tmp_path):
        """Cyclic graph returns error message."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        scripts = [
            {"script_id": "a", "dependencies": ["c"]},
            {"script_id": "b", "dependencies": ["a"]},
            {"script_id": "c", "dependencies": ["b"]},
        ]
        errors = generator.validate_dependencies(scripts)
        assert len(errors) > 0
        assert "cyclic" in errors[0].lower() or "Cyclic" in errors[0]

    def test_self_reference_detected(self, tmp_path):
        """Self-referencing dependency is detected."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        scripts = [
            {"script_id": "a", "dependencies": ["a"]},
        ]
        errors = generator.validate_dependencies(scripts)
        assert len(errors) > 0


class TestDAGGeneratorRemove:
    """DAG file removal."""

    def test_remove_existing_dag(self, tmp_path):
        """Remove returns True for existing file."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        script = {"script_id": "to_remove", "source": "akshare", "timeout": 300, "category": "test"}
        generator.generate_dag(script)
        assert generator.remove_dag("to_remove") is True
        assert not (tmp_path / "dag_to_remove.py").exists()

    def test_remove_nonexistent_dag(self, tmp_path):
        """Remove returns False for missing file."""
        generator = DAGGenerator(dag_output_dir=str(tmp_path))
        assert generator.remove_dag("nonexistent") is False
