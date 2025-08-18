#!/usr/bin/env python3
"""
Test script to validate CDK synthesis without requiring AWS credentials
"""

import sys
import os

# Add infra directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'infra'))

def test_imports():
    """Test that all modules can be imported"""
    try:
        print("Testing imports...")
        
        # Test construct imports
        from constructs.sqs_with_dlq import SqsWithDlq
        print("✅ SqsWithDlq import successful")
        
        from constructs.lambda_fn import ObservableLambda
        print("✅ ObservableLambda import successful")
        
        from constructs.event_bus import IngestionEventBus
        print("✅ IngestionEventBus import successful")
        
        from constructs.dashboard import IngestionDashboard
        print("✅ IngestionDashboard import successful")
        
        from constructs.alarms import IngestionAlarms
        print("✅ IngestionAlarms import successful")
        
        # Test stack imports
        from stacks.queue_stack import QueueStack
        print("✅ QueueStack import successful")
        
        from stacks.functions_stack import FunctionsStack
        print("✅ FunctionsStack import successful")
        
        from stacks.api_stack import ApiStack
        print("✅ ApiStack import successful")
        
        from stacks.observability_stack import ObservabilityStack
        print("✅ ObservabilityStack import successful")
        
        print("\n🎉 All imports successful!")
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_app_syntax():
    """Test that app.py has valid syntax"""
    try:
        print("\nTesting app.py syntax...")
        import py_compile
        py_compile.compile('infra/app.py', doraise=True)
        print("✅ app.py syntax is valid")
        return True
    except py_compile.PyCompileError as e:
        print(f"❌ Syntax error in app.py: {e}")
        return False

if __name__ == "__main__":
    print("🔍 CDK Project Validation")
    print("=" * 40)
    
    # Check if we have CDK installed
    try:
        import aws_cdk
        print(f"✅ AWS CDK version: {aws_cdk.__version__}")
    except ImportError:
        print("❌ AWS CDK not installed. Run: pip install -r infra/requirements.txt")
        sys.exit(1)
    
    success = True
    
    # Test syntax
    if not test_app_syntax():
        success = False
    
    # Test imports
    if not test_imports():
        success = False
    
    if success:
        print("\n🎉 Project should be able to run 'cdk synth'!")
        print("\nNext steps:")
        print("1. cd infra")
        print("2. pip install -r requirements.txt")
        print("3. cdk synth")
    else:
        print("\n❌ Project has issues that need to be fixed before running 'cdk synth'")
        sys.exit(1)