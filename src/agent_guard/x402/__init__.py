"""x402 v2 exact/EVM EIP-3009 local test-chain payment integration.

Modules with heavy dependencies (``signer``, ``facilitator``, ``localchain``,
``client``, ``resource``, ``gate``, ``accept``) import the official ``x402``
SDK and/or local EVM tooling; they are imported explicitly, never from this
package root, so contract and wire tests stay runnable without the runtime
image.
"""
