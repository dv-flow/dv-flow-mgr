"""Tests for lsf_job: bsub command building, output parsing. All mocked."""
import pytest
from unittest.mock import patch, MagicMock
from dv_flow.mgr.lsf_job import (
    build_bsub_cmd, bsub_submit, bjobs_query, bkill, _memory_to_mb,
)
from dv_flow.mgr.runner_backend import ResourceReq
from dv_flow.mgr.runner_config import LsfConfig


class TestMemoryToMb:
    def test_gigabytes(self):
        assert _memory_to_mb("4G") == 4096

    def test_megabytes(self):
        assert _memory_to_mb("512M") == 512

    def test_terabytes(self):
        assert _memory_to_mb("1T") == 1048576

    def test_plain_number(self):
        assert _memory_to_mb("2048") == 2048

    def test_lowercase(self):
        assert _memory_to_mb("4g") == 4096


class TestBuildBsubCmd:
    def test_uses_bsub_cmd_from_config(self):
        cfg = LsfConfig(bsub_cmd="lsf_bsub")
        cmd = build_bsub_cmd(ResourceReq(), cfg, "host:9100")
        assert cmd[0] == "lsf_bsub"

    def test_includes_queue(self):
        cfg = LsfConfig(queue="regr_high")
        cmd = build_bsub_cmd(ResourceReq(), cfg, "host:9100")
        assert "-q" in cmd
        idx = cmd.index("-q")
        assert cmd[idx + 1] == "regr_high"

    def test_includes_project(self):
        cfg = LsfConfig(project="nbio-pcie")
        cmd = build_bsub_cmd(ResourceReq(), cfg, "host:9100")
        assert "-P" in cmd
        idx = cmd.index("-P")
        assert cmd[idx + 1] == "nbio-pcie"

    def test_includes_cores_and_memory(self):
        req = ResourceReq(cores=4, memory="8G")
        cmd = build_bsub_cmd(req, LsfConfig(), "host:9100")
        assert "-n" in cmd
        assert "4" in cmd
        assert "-M" in cmd
        assert "8G" in cmd

    def test_rusage_mem(self):
        req = ResourceReq(memory="4G")
        cmd = build_bsub_cmd(req, LsfConfig(), "host:9100")
        # Should have -R "rusage[mem=4096]"
        r_args = [cmd[i + 1] for i in range(len(cmd)) if cmd[i] == "-R"]
        assert any("rusage[mem=4096]" in r for r in r_args)

    def test_resource_select_accumulated(self):
        req = ResourceReq(resource_select=["type==RHEL8_64", "mem>4000"])
        cmd = build_bsub_cmd(req, LsfConfig(), "host:9100")
        r_args = [cmd[i + 1] for i in range(len(cmd)) if cmd[i] == "-R"]
        select_args = [r for r in r_args if "select[" in r]
        assert len(select_args) == 1
        assert "type==RHEL8_64" in select_args[0]
        assert "mem>4000" in select_args[0]

    def test_bsub_extra_appended(self):
        cfg = LsfConfig(bsub_extra=["-G", "dv_users"])
        cmd = build_bsub_cmd(ResourceReq(), cfg, "host:9100")
        assert "-G" in cmd
        assert "dv_users" in cmd

    def test_empty_queue_omitted(self):
        cfg = LsfConfig(queue="")
        cmd = build_bsub_cmd(ResourceReq(), cfg, "host:9100")
        assert "-q" not in cmd

    def test_empty_project_omitted(self):
        cfg = LsfConfig(project="")
        cmd = build_bsub_cmd(ResourceReq(), cfg, "host:9100")
        assert "-P" not in cmd

    def test_resource_class_in_worker_cmd(self):
        """resource_class is appended as separate --resource-class <class> args."""
        cmd = build_bsub_cmd(ResourceReq(), LsfConfig(),
                             ["dfm", "worker", "--connect", "host:9100"],
                             resource_class="medium")
        assert cmd[-2] == "--resource-class"
        assert cmd[-1] == "medium"


class TestBsubSubmit:
    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_parse_job_id(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Job <12345> is submitted to queue <normal>.\n",
            stderr="",
        )
        job_id = bsub_submit(["bsub", "echo", "hello"])
        assert job_id == "12345"

    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_bsub_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="No such queue"
        )
        with pytest.raises(RuntimeError, match="bsub failed"):
            bsub_submit(["bsub", "echo"])


class TestBjobsQuery:
    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_pend(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="PEND\n", stderr="")
        assert bjobs_query("123") == "PEND"

    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_run(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="RUN\n", stderr="")
        assert bjobs_query("123") == "RUN"

    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_done(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="DONE\n", stderr="")
        assert bjobs_query("123") == "DONE"

    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="EXIT\n", stderr="")
        assert bjobs_query("123") == "EXIT"

    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        assert bjobs_query("123") == "UNKNOWN"


class TestBkill:
    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert bkill("123") is True

    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        assert bkill("123") is False

    @patch("dv_flow.mgr.lsf_job.subprocess.run")
    def test_builds_correct_cmd(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        bkill("99999", bkill_cmd="lsf_bkill")
        mock_run.assert_called_once_with(["lsf_bkill", "99999"],
                                          capture_output=True, text=True)
