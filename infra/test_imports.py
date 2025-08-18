#!/usr/bin/env python3
import sys
import os

print("Python path:")
for path in sys.path:
    print(f"  {path}")

try:
    import constructs

    print("Successfully imported constructs")
    print(f"constructs location: {constructs.__file__}")
except Exception as e:
    print(f"Failed to import constructs: {e}")

try:
    import constructs._jsii

    print("Successfully imported constructs._jsii")
except Exception as e:
    print(f"Failed to import constructs._jsii: {e}")

try:
    import aws_cdk

    print("Successfully imported aws_cdk")
    print(f"aws_cdk location: {aws_cdk.__file__}")
except Exception as e:
    print(f"Failed to import aws_cdk: {e}")
