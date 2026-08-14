//! Narrow, process-shared primitives for the LYIP native transport.
//!
//! This crate deliberately exposes no routing or message model.  A ring has
//! exactly one producer and one consumer.  Publication is controlled by a
//! per-slot sequence number, so payload bytes are only read after an Acquire
//! load observes the producer's Release store.

use std::fmt::Write as _;
use std::ptr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyType};

#[cfg(target_os = "windows")]
use std::ffi::c_void;
#[cfg(target_os = "windows")]
use std::os::windows::ffi::OsStrExt;

const LYIP_NATIVE_ABI: u32 = 1;
const RING_VERSION: u32 = 1;
const HEADER_SIZE: usize = 64;
const SLOT_PREFIX_SIZE: usize = 16;
const READY_MAGIC: u64 = 0x4c59_4950_5350_5343; // "LYIPSPSC"
const MAX_CAPACITY: usize = 1 << 20;
const MAX_SLOT_SIZE: usize = 1 << 20;
const MAX_MAPPING_SIZE: usize = u32::MAX as usize;

const STATE_OFFSET: usize = 0;
const VERSION_OFFSET: usize = 8;
const HEADER_SIZE_OFFSET: usize = 12;
const CAPACITY_OFFSET: usize = 16;
const SLOT_SIZE_OFFSET: usize = 24;
const PRODUCER_OFFSET: usize = 32;
const CONSUMER_OFFSET: usize = 40;
const STRIDE_OFFSET: usize = 48;
const TOTAL_SIZE_OFFSET: usize = 56;

#[derive(Debug, Clone, Copy)]
struct RingLayout {
    capacity: usize,
    slot_size: usize,
    stride: usize,
    total_size: usize,
}

#[cfg(target_os = "windows")]
struct SharedMapping {
    handle: isize,
    pointer: *mut u8,
    size: usize,
}

#[cfg(target_os = "windows")]
impl SharedMapping {
    fn create(name: &str, size: usize) -> Result<Self, String> {
        if size > MAX_MAPPING_SIZE {
            return Err("shared-memory ring exceeds the supported Windows mapping size".to_owned());
        }
        let name = wide_name(name);
        let handle = unsafe {
            CreateFileMappingW(
                -1,
                ptr::null(),
                PAGE_READWRITE,
                0,
                size as u32,
                name.as_ptr(),
            )
        };
        if handle == 0 {
            return Err(last_windows_error("cannot create shared-memory mapping"));
        }
        if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
            unsafe { CloseHandle(handle) };
            return Err("shared-memory mapping name already exists".to_owned());
        }
        unsafe { Self::map(handle, size) }
    }

    fn open(name: &str) -> Result<Self, String> {
        let name = wide_name(name);
        let handle = unsafe { OpenFileMappingW(FILE_MAP_ALL_ACCESS, 0, name.as_ptr()) };
        if handle == 0 {
            return Err(last_windows_error("cannot open shared-memory mapping"));
        }
        let header = unsafe { Self::map(handle, HEADER_SIZE) }?;
        let total_size = unsafe { read_u64(header.pointer.add(TOTAL_SIZE_OFFSET)) } as usize;
        if !(HEADER_SIZE..=MAX_MAPPING_SIZE).contains(&total_size) {
            return Err("shared-memory mapping has an invalid declared size".to_owned());
        }
        unsafe { header.remap(total_size) }
    }

    unsafe fn map(handle: isize, size: usize) -> Result<Self, String> {
        let pointer =
            unsafe { MapViewOfFile(handle, FILE_MAP_ALL_ACCESS, 0, 0, size) }.cast::<u8>();
        if pointer.is_null() {
            unsafe { CloseHandle(handle) };
            return Err(last_windows_error("cannot map shared-memory view"));
        }
        Ok(Self {
            handle,
            pointer,
            size,
        })
    }

    unsafe fn remap(mut self, size: usize) -> Result<Self, String> {
        let handle = self.handle;
        unsafe { UnmapViewOfFile(self.pointer.cast()) };
        self.pointer = ptr::null_mut();
        self.handle = 0;
        std::mem::forget(self);
        unsafe { Self::map(handle, size) }
    }

    fn as_ptr(&self) -> *mut u8 {
        self.pointer
    }

    fn len(&self) -> usize {
        self.size
    }
}

#[cfg(target_os = "windows")]
impl Drop for SharedMapping {
    fn drop(&mut self) {
        unsafe {
            UnmapViewOfFile(self.pointer.cast());
            CloseHandle(self.handle);
        }
    }
}

#[cfg(target_os = "windows")]
const PAGE_READWRITE: u32 = 0x04;
#[cfg(target_os = "windows")]
const FILE_MAP_ALL_ACCESS: u32 = 0x000f_001f;
#[cfg(target_os = "windows")]
const ERROR_ALREADY_EXISTS: u32 = 183;

#[cfg(target_os = "windows")]
unsafe extern "system" {
    fn CreateFileMappingW(
        file: isize,
        attributes: *const c_void,
        protect: u32,
        maximum_size_high: u32,
        maximum_size_low: u32,
        name: *const u16,
    ) -> isize;
    fn OpenFileMappingW(desired_access: u32, inherit_handle: i32, name: *const u16) -> isize;
    fn MapViewOfFile(
        mapping: isize,
        desired_access: u32,
        file_offset_high: u32,
        file_offset_low: u32,
        number_of_bytes: usize,
    ) -> *mut c_void;
    fn UnmapViewOfFile(address: *const c_void) -> i32;
    fn CloseHandle(handle: isize) -> i32;
    fn GetLastError() -> u32;
}

#[cfg(target_os = "windows")]
fn wide_name(name: &str) -> Vec<u16> {
    std::ffi::OsStr::new(name)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect()
}

#[cfg(target_os = "windows")]
fn last_windows_error(context: &str) -> String {
    format!("{context} (Windows error {})", unsafe { GetLastError() })
}

#[cfg(not(target_os = "windows"))]
struct SharedMapping;

#[cfg(not(target_os = "windows"))]
impl SharedMapping {
    fn create(_name: &str, _size: usize) -> Result<Self, String> {
        Err("shared-memory primitives are not implemented for this native target".to_owned())
    }

    fn open(_name: &str) -> Result<Self, String> {
        Err("shared-memory primitives are not implemented for this native target".to_owned())
    }

    fn as_ptr(&self) -> *mut u8 {
        std::ptr::null_mut()
    }

    fn len(&self) -> usize {
        0
    }
}

impl RingLayout {
    fn new(capacity: usize, slot_size: usize) -> Result<Self, String> {
        if capacity == 0 || capacity > MAX_CAPACITY {
            return Err(format!("capacity must be in 1..={MAX_CAPACITY}"));
        }
        if slot_size == 0 || slot_size > MAX_SLOT_SIZE {
            return Err(format!("slot_size must be in 1..={MAX_SLOT_SIZE}"));
        }
        let stride = SLOT_PREFIX_SIZE
            .checked_add(slot_size)
            .and_then(align_to_atomic)
            .ok_or_else(|| "slot layout overflows usize".to_owned())?;
        let total_size = HEADER_SIZE
            .checked_add(
                capacity
                    .checked_mul(stride)
                    .ok_or_else(|| "ring layout overflows usize".to_owned())?,
            )
            .ok_or_else(|| "ring layout overflows usize".to_owned())?;
        if total_size > MAX_MAPPING_SIZE {
            return Err("ring layout exceeds the supported mapping size".to_owned());
        }
        Ok(Self {
            capacity,
            slot_size,
            stride,
            total_size,
        })
    }
}

fn align_to_atomic(value: usize) -> Option<usize> {
    let alignment = std::mem::align_of::<AtomicU64>();
    value
        .checked_add(alignment - 1)
        .map(|value| value & !(alignment - 1))
}

/// Fixed-size shared-memory SPSC ring.  The name is the OS shared-memory
/// handle; a supervised child receives it out of band and calls `open`.
struct SharedSpscRing {
    mapping: SharedMapping,
    layout: RingLayout,
    name: String,
}

impl SharedSpscRing {
    fn create(name: String, capacity: usize, slot_size: usize) -> Result<Self, String> {
        validate_name(&name)?;
        let layout = RingLayout::new(capacity, slot_size)?;
        let mapping = SharedMapping::create(&name, layout.total_size)?;
        let ring = Self {
            mapping,
            layout,
            name,
        };
        ring.initialize();
        Ok(ring)
    }

    fn open(name: String) -> Result<Self, String> {
        validate_name(&name)?;
        let mapping = SharedMapping::open(&name)?;
        let ring = Self {
            mapping,
            layout: RingLayout {
                capacity: 0,
                slot_size: 0,
                stride: 0,
                total_size: 0,
            },
            name,
        };
        let layout = ring.read_layout()?;
        if ring.mapping.len() < layout.total_size {
            return Err(
                "shared-memory ring mapping is shorter than its header declares".to_owned(),
            );
        }
        Ok(Self { layout, ..ring })
    }

    fn initialize(&self) {
        // A zero state makes concurrent openers wait until all fields and slot
        // sequences are initialized.  The final Release store publishes them.
        unsafe {
            self.state().store(0, Ordering::Relaxed);
            write_u32(self.base().add(VERSION_OFFSET), RING_VERSION);
            write_u32(self.base().add(HEADER_SIZE_OFFSET), HEADER_SIZE as u32);
            write_u64(
                self.base().add(CAPACITY_OFFSET),
                self.layout.capacity as u64,
            );
            write_u64(
                self.base().add(SLOT_SIZE_OFFSET),
                self.layout.slot_size as u64,
            );
            self.producer().store(0, Ordering::Relaxed);
            self.consumer().store(0, Ordering::Relaxed);
            write_u64(self.base().add(STRIDE_OFFSET), self.layout.stride as u64);
            write_u64(
                self.base().add(TOTAL_SIZE_OFFSET),
                self.layout.total_size as u64,
            );
            for index in 0..self.layout.capacity {
                self.slot_sequence(index)
                    .store((index as u64).wrapping_mul(2), Ordering::Relaxed);
                self.slot_length(index).store(0, Ordering::Relaxed);
            }
            self.state().store(READY_MAGIC, Ordering::Release);
        }
    }

    fn read_layout(&self) -> Result<RingLayout, String> {
        if self.mapping.len() < HEADER_SIZE {
            return Err("shared-memory ring header is truncated".to_owned());
        }
        if self.state().load(Ordering::Acquire) != READY_MAGIC {
            return Err("shared-memory ring is not initialized by its owner".to_owned());
        }
        let version = unsafe { read_u32(self.base().add(VERSION_OFFSET)) };
        let header_size = unsafe { read_u32(self.base().add(HEADER_SIZE_OFFSET)) };
        if version != RING_VERSION || header_size as usize != HEADER_SIZE {
            return Err("shared-memory ring ABI is incompatible".to_owned());
        }
        let capacity = unsafe { read_u64(self.base().add(CAPACITY_OFFSET)) } as usize;
        let slot_size = unsafe { read_u64(self.base().add(SLOT_SIZE_OFFSET)) } as usize;
        let expected = RingLayout::new(capacity, slot_size)?;
        let stride = unsafe { read_u64(self.base().add(STRIDE_OFFSET)) } as usize;
        let total_size = unsafe { read_u64(self.base().add(TOTAL_SIZE_OFFSET)) } as usize;
        if stride != expected.stride || total_size != expected.total_size {
            return Err("shared-memory ring layout checksum is invalid".to_owned());
        }
        Ok(expected)
    }

    fn try_push(&self, payload: &[u8]) -> Result<bool, String> {
        if payload.len() > self.layout.slot_size {
            return Err(format!(
                "payload length {} exceeds fixed slot size {}",
                payload.len(),
                self.layout.slot_size
            ));
        }
        let position = self.producer().load(Ordering::Relaxed);
        let slot = self.slot_index(position);
        if self.slot_sequence(slot).load(Ordering::Acquire) != position.wrapping_mul(2) {
            return Ok(false);
        }
        unsafe {
            ptr::copy_nonoverlapping(payload.as_ptr(), self.slot_payload(slot), payload.len());
        }
        self.slot_length(slot)
            .store(payload.len() as u64, Ordering::Relaxed);
        self.slot_sequence(slot)
            .store(position.wrapping_mul(2).wrapping_add(1), Ordering::Release);
        self.producer()
            .store(position.wrapping_add(1), Ordering::Relaxed);
        Ok(true)
    }

    fn try_pop(&self) -> Result<Option<Vec<u8>>, String> {
        let position = self.consumer().load(Ordering::Relaxed);
        let slot = self.slot_index(position);
        if self.slot_sequence(slot).load(Ordering::Acquire)
            != position.wrapping_mul(2).wrapping_add(1)
        {
            return Ok(None);
        }
        let length = self.slot_length(slot).load(Ordering::Relaxed) as usize;
        if length > self.layout.slot_size {
            return Err("shared-memory ring slot length is corrupt".to_owned());
        }
        let mut payload = vec![0; length];
        unsafe {
            ptr::copy_nonoverlapping(self.slot_payload(slot), payload.as_mut_ptr(), length);
        }
        self.slot_sequence(slot).store(
            position
                .wrapping_add(self.layout.capacity as u64)
                .wrapping_mul(2),
            Ordering::Release,
        );
        self.consumer()
            .store(position.wrapping_add(1), Ordering::Relaxed);
        Ok(Some(payload))
    }

    fn base(&self) -> *mut u8 {
        self.mapping.as_ptr()
    }

    fn state(&self) -> &AtomicU64 {
        unsafe { &*(self.base().add(STATE_OFFSET).cast::<AtomicU64>()) }
    }

    fn producer(&self) -> &AtomicU64 {
        unsafe { &*(self.base().add(PRODUCER_OFFSET).cast::<AtomicU64>()) }
    }

    fn consumer(&self) -> &AtomicU64 {
        unsafe { &*(self.base().add(CONSUMER_OFFSET).cast::<AtomicU64>()) }
    }

    fn slot_index(&self, position: u64) -> usize {
        position as usize % self.layout.capacity
    }

    fn slot_sequence(&self, slot: usize) -> &AtomicU64 {
        unsafe {
            &*(self
                .base()
                .add(HEADER_SIZE + slot * self.layout.stride)
                .cast::<AtomicU64>())
        }
    }

    fn slot_length(&self, slot: usize) -> &AtomicU64 {
        unsafe {
            &*(self
                .base()
                .add(HEADER_SIZE + slot * self.layout.stride + std::mem::size_of::<AtomicU64>())
                .cast::<AtomicU64>())
        }
    }

    fn slot_payload(&self, slot: usize) -> *mut u8 {
        self.base()
            .wrapping_add(HEADER_SIZE + slot * self.layout.stride + SLOT_PREFIX_SIZE)
    }
}

fn validate_name(name: &str) -> Result<(), String> {
    if name.is_empty() || name.len() > 180 || name.bytes().any(|byte| byte == 0) {
        return Err(
            "shared-memory name must be a non-empty UTF-8 string shorter than 181 bytes".to_owned(),
        );
    }
    Ok(())
}

unsafe fn write_u32(address: *mut u8, value: u32) {
    unsafe { ptr::write_unaligned(address.cast::<u32>(), value) };
}

unsafe fn write_u64(address: *mut u8, value: u64) {
    unsafe { ptr::write_unaligned(address.cast::<u64>(), value) };
}

unsafe fn read_u32(address: *const u8) -> u32 {
    unsafe { ptr::read_unaligned(address.cast::<u32>()) }
}

unsafe fn read_u64(address: *const u8) -> u64 {
    unsafe { ptr::read_unaligned(address.cast::<u64>()) }
}

fn probe_name() -> String {
    let mut name = String::from("lyip-native-probe-");
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_nanos());
    let _ = write!(&mut name, "{}-{nanos}", std::process::id());
    name
}

#[pyclass(
    name = "SharedSpscRing",
    module = "liteyukibot_ipc_native._native",
    unsendable
)]
struct PySharedSpscRing {
    ring: SharedSpscRing,
}

#[pymethods]
impl PySharedSpscRing {
    #[new]
    fn new(name: String, capacity: usize, slot_size: usize) -> PyResult<Self> {
        SharedSpscRing::create(name, capacity, slot_size)
            .map(|ring| Self { ring })
            .map_err(PyRuntimeError::new_err)
    }

    #[classmethod]
    fn open(_cls: &Bound<'_, PyType>, name: String) -> PyResult<Self> {
        SharedSpscRing::open(name)
            .map(|ring| Self { ring })
            .map_err(PyRuntimeError::new_err)
    }

    #[getter]
    fn name(&self) -> &str {
        &self.ring.name
    }

    #[getter]
    fn capacity(&self) -> usize {
        self.ring.layout.capacity
    }

    #[getter]
    fn slot_size(&self) -> usize {
        self.ring.layout.slot_size
    }

    fn try_push(&self, payload: &[u8]) -> PyResult<bool> {
        self.ring.try_push(payload).map_err(PyValueError::new_err)
    }

    fn try_pop<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyBytes>>> {
        self.ring
            .try_pop()
            .map(|payload| payload.map(|payload| PyBytes::new(py, &payload)))
            .map_err(PyRuntimeError::new_err)
    }
}

#[pyfunction]
fn lyip_native_abi() -> u32 {
    LYIP_NATIVE_ABI
}

#[pyfunction]
fn shared_memory_available() -> bool {
    SharedSpscRing::create(probe_name(), 1, 1).is_ok()
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PySharedSpscRing>()?;
    module.add_function(wrap_pyfunction!(lyip_native_abi, module)?)?;
    module.add_function(wrap_pyfunction!(shared_memory_available, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn name(label: &str) -> String {
        format!("lyip-native-test-{label}-{}", probe_name())
    }

    #[test]
    fn shared_handles_publish_payloads_in_order() {
        let owner = SharedSpscRing::create(name("visibility"), 3, 8).unwrap();
        let peer = SharedSpscRing::open(owner.name.clone()).unwrap();
        assert!(owner.try_push(b"first").unwrap());
        assert!(owner.try_push(b"second").unwrap());
        assert_eq!(peer.try_pop().unwrap(), Some(b"first".to_vec()));
        assert_eq!(peer.try_pop().unwrap(), Some(b"second".to_vec()));
        assert_eq!(peer.try_pop().unwrap(), None);
    }

    #[test]
    fn full_ring_rejects_then_wraps() {
        let ring = SharedSpscRing::create(name("wrap"), 2, 4).unwrap();
        assert!(ring.try_push(b"a").unwrap());
        assert!(ring.try_push(b"b").unwrap());
        assert!(!ring.try_push(b"c").unwrap());
        assert_eq!(ring.try_pop().unwrap(), Some(b"a".to_vec()));
        assert!(ring.try_push(b"c").unwrap());
        assert_eq!(ring.try_pop().unwrap(), Some(b"b".to_vec()));
        assert_eq!(ring.try_pop().unwrap(), Some(b"c".to_vec()));
    }

    #[test]
    fn rejects_payload_larger_than_slot() {
        let ring = SharedSpscRing::create(name("bounds"), 1, 2).unwrap();
        assert!(ring.try_push(b"abc").is_err());
    }

    #[test]
    fn independent_rings_isolate_control_capacity() {
        let business = SharedSpscRing::create(name("business"), 1, 4).unwrap();
        let control = SharedSpscRing::create(name("control"), 1, 4).unwrap();
        assert!(business.try_push(b"data").unwrap());
        assert!(!business.try_push(b"more").unwrap());
        assert!(control.try_push(b"ack").unwrap());
        assert_eq!(control.try_pop().unwrap(), Some(b"ack".to_vec()));
    }
}
