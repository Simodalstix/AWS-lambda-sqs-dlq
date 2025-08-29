"""
Test that CDK app synthesizes successfully
"""
import subprocess
import sys
import os
from pathlib import Path


def test_cdk_synth():
    """Test that CDK synth succeeds without errors"""
    infra_dir = Path(__file__).parent.parent
    
    env = os.environ.copy()
    env.update({
        "AWS_DEFAULT_REGION": "us-east-1", 
        "AWS_ACCOUNT_ID": "123456789012",
        "JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION": "1"
    })
    
    result = subprocess.run(
        [sys.executable, "app.py"],
        cwd=infra_dir,
        capture_output=True,
        text=True,
        env=env
    )
    
    # CDK synth should succeed (exit code 0)
    assert result.returncode == 0, f"CDK synth failed with exit code {result.returncode}. stderr: {result.stderr}"


def test_basic_imports():
    """Test that basic CDK imports work"""
    try:
        import aws_cdk as cdk
        import constructs
        # Just test that imports work, don't check versions
        assert hasattr(cdk, 'App')
        assert hasattr(constructs, 'Construct')
    except ImportError as e:
        assert False, f"Failed to import CDK dependencies: {e}"
