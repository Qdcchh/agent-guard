//! Standalone teaching prototype. No gateway integration or production key storage.

use frost_ed25519 as frost;
use rand::rngs::OsRng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashSet};

const DOMAIN: &[u8] = b"AGENT-GUARD-THRESHOLD-ACTION-V1\n";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OrderItem {
    pub sku: String,
    pub quantity: u16,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OrderAction {
    pub version: u8,
    pub tenant_id: String,
    pub task_id: String,
    pub root_grant_id: String,
    pub grant_id: String,
    pub holder_client_id: String,
    pub holder_kid: String,
    pub audience: String,
    pub tool_id: String,
    pub currency: String,
    pub policy_version: u32,
    pub key_epoch: u32,
    pub action_id: String,
    pub idempotency_key: String,
    pub request_id: String,
    pub quote_id: String,
    pub quote_version: String,
    pub items: Vec<OrderItem>,
    pub delivery_id: String,
    pub amount_fen: u64,
    pub canonical_params_sha256: String,
    pub expires_at: u64,
}

#[derive(Serialize)]
struct OrderParameters<'a> {
    request_id: &'a str,
    quote_id: &'a str,
    quote_version: &'a str,
    items: &'a [OrderItem],
    delivery_id: &'a str,
}

impl OrderAction {
    /// Digest of the full fixed order parameter structure in this prototype.
    pub fn compute_params_digest(&self) -> Result<String, DemoError> {
        let params = OrderParameters {
            request_id: &self.request_id,
            quote_id: &self.quote_id,
            quote_version: &self.quote_version,
            items: &self.items,
            delivery_id: &self.delivery_id,
        };
        let bytes = serde_json::to_vec(&params).map_err(|_| DemoError::InvalidAction)?;
        Ok(hex::encode(Sha256::digest(bytes)))
    }

    pub fn message(&self) -> Result<Vec<u8>, DemoError> {
        self.validate()?;
        let mut message = DOMAIN.to_vec();
        message.extend(serde_json::to_vec(self).map_err(|_| DemoError::InvalidAction)?);
        Ok(message)
    }

    fn validate(&self) -> Result<(), DemoError> {
        if self.version != 1
            || self.tool_id != "procurement.order.create"
            || self.currency != "CNY"
            || self.policy_version == 0
            || self.key_epoch == 0
            || self.items.is_empty()
            || self.items.len() > 256
            || self.items.iter().any(|item| {
                item.quantity == 0
                    || item.sku.is_empty()
                    || item.sku.len() > 128
                    || !item
                        .sku
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b"._:-@".contains(&byte))
            })
            || self
                .items
                .iter()
                .map(|item| &item.sku)
                .collect::<HashSet<_>>()
                .len()
                != self.items.len()
            || self.amount_fen > 9_007_199_254_740_991
            || self.expires_at == 0
            || self.canonical_params_sha256 != self.compute_params_digest()?
            || [
                &self.tenant_id,
                &self.task_id,
                &self.root_grant_id,
                &self.grant_id,
                &self.holder_client_id,
                &self.holder_kid,
                &self.audience,
                &self.action_id,
                &self.idempotency_key,
                &self.request_id,
                &self.quote_id,
                &self.quote_version,
                &self.delivery_id,
            ]
            .iter()
            .any(|value| {
                value.is_empty()
                    || value.len() > 128
                    || !value
                        .bytes()
                        .all(|byte| byte.is_ascii_alphanumeric() || b"._:-@".contains(&byte))
            })
        {
            return Err(DemoError::InvalidAction);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DemoError {
    InvalidAction,
    Expired,
    TooFewSigners,
    DuplicateSigner,
    WrongAction,
    InvalidSignature,
    AlreadyAccepted,
    Frost,
}

impl std::fmt::Display for DemoError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{self:?}")
    }
}

impl std::error::Error for DemoError {}

impl From<frost::Error> for DemoError {
    fn from(_: frost::Error) -> Self {
        Self::Frost
    }
}

/// One owner of one dealer-generated key share. The full secret is never reconstructed.
pub struct Signer {
    id: frost::Identifier,
    key: frost::keys::KeyPackage,
}

impl Signer {
    pub fn id(&self) -> frost::Identifier {
        self.id
    }

    pub fn commit(&self) -> PendingSigner<'_> {
        let (nonces, commitments) = frost::round1::commit(self.key.signing_share(), &mut OsRng);
        PendingSigner {
            signer: self,
            nonces,
            commitments,
        }
    }
}

/// One-use nonce holder. Consuming this value prevents accidental local nonce reuse.
pub struct PendingSigner<'a> {
    signer: &'a Signer,
    nonces: frost::round1::SigningNonces,
    commitments: frost::round1::SigningCommitments,
}

impl PendingSigner<'_> {
    pub fn id(&self) -> frost::Identifier {
        self.signer.id
    }

    pub fn commitments(&self) -> frost::round1::SigningCommitments {
        self.commitments
    }

    pub fn sign(
        self,
        action: &OrderAction,
        now: u64,
        package: &frost::SigningPackage,
    ) -> Result<frost::round2::SignatureShare, DemoError> {
        if action.expires_at <= now {
            return Err(DemoError::Expired);
        }
        if *package.message() != action.message()? {
            return Err(DemoError::WrongAction);
        }
        Ok(frost::round2::sign(
            package,
            &self.nonces,
            &self.signer.key,
        )?)
    }
}

pub struct GroupPublic {
    package: frost::keys::PublicKeyPackage,
}

impl GroupPublic {
    pub fn verify(
        &self,
        action: &OrderAction,
        signature: &frost::Signature,
    ) -> Result<(), DemoError> {
        self.package
            .verifying_key()
            .verify(&action.message()?, signature)
            .map_err(|_| DemoError::InvalidSignature)
    }
}

/// Explicit trusted-dealer setup for this demo only. Return values must be separated by owner.
pub fn trusted_dealer_setup() -> Result<(Vec<Signer>, GroupPublic), DemoError> {
    let (shares, package) =
        frost::keys::generate_with_dealer(3, 2, frost::keys::IdentifierList::Default, &mut OsRng)?;
    let mut signers = Vec::with_capacity(3);
    for (id, share) in shares {
        signers.push(Signer {
            id,
            key: frost::keys::KeyPackage::try_from(share)?,
        });
    }
    Ok((signers, GroupPublic { package }))
}

/// Coordinator sees commitments and shares, never signer keys. Caller supplies two distinct signers.
pub fn sign_action(
    action: &OrderAction,
    now: u64,
    pending: Vec<PendingSigner<'_>>,
    public: &GroupPublic,
) -> Result<frost::Signature, DemoError> {
    if action.expires_at <= now {
        return Err(DemoError::Expired);
    }
    if pending.len() < 2 {
        return Err(DemoError::TooFewSigners);
    }
    let mut commitments = BTreeMap::new();
    for signer in &pending {
        if commitments
            .insert(signer.id(), signer.commitments())
            .is_some()
        {
            return Err(DemoError::DuplicateSigner);
        }
    }
    let package = frost::SigningPackage::new(commitments, &action.message()?);
    let mut shares = BTreeMap::new();
    for signer in pending {
        let id = signer.id();
        shares.insert(id, signer.sign(action, now, &package)?);
    }
    let signature = frost::aggregate(&package, &shares, &public.package)?;
    public.verify(action, &signature)?;
    Ok(signature)
}

/// Demonstrates checks immediately before acceptance. A gateway must replace this set with
/// atomic persistent state and additionally recheck grant/ancestor revocation and budget.
pub struct DemoActionGate {
    public: GroupPublic,
    accepted_actions: HashSet<(String, String, String)>,
    accepted_business_keys: HashSet<(String, String, String)>,
}

impl DemoActionGate {
    pub fn new(public: GroupPublic) -> Self {
        Self {
            public,
            accepted_actions: HashSet::new(),
            accepted_business_keys: HashSet::new(),
        }
    }

    pub fn accept(
        &mut self,
        action: &OrderAction,
        signature: &frost::Signature,
        now: u64,
    ) -> Result<(), DemoError> {
        if action.expires_at <= now {
            return Err(DemoError::Expired);
        }
        self.public.verify(action, signature)?;
        let action_key = (
            action.tenant_id.clone(),
            action.task_id.clone(),
            action.action_id.clone(),
        );
        let business_key = (
            action.tenant_id.clone(),
            action.task_id.clone(),
            action.idempotency_key.clone(),
        );
        if self.accepted_actions.contains(&action_key)
            || self.accepted_business_keys.contains(&business_key)
        {
            return Err(DemoError::AlreadyAccepted);
        }
        self.accepted_actions.insert(action_key);
        self.accepted_business_keys.insert(business_key);
        Ok(())
    }
}
