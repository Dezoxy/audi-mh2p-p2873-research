# CarPlay cluster path — static scope (2026-09-17)

The user uses CarPlay only. This scopes what is reachable for a Waze-in-cluster
goal on CarPlay, from static evidence, with no vehicle. Nothing here is
approved for installation, and none of it is confirmed against this specific
car's binaries (card 1 skipped the capture; see the version-mismatch note).

## Three tiers, ranked by how solved they are

| Tier | What it shows in the cockpit | CarPlay status |
|---|---|---|
| Guidance data | Arrows, distance to turn, street, lane guidance | Real path: `dio_manager_preload.c` parses iAP2 route-guidance TLVs and writes `/tmp/cluster_cp.state` for the Java side. |
| Screen mirror | Whatever CarPlay draws on the main screen | Upstream main-branch behaviour. |
| Independent map raster | A live map behind the wheel while the MMI shows another app | Unsolved for CarPlay. Only samueljiahua's unfinished probe attempts it. Android-Auto-only in practice. |

The user's literal goal ("Waze as its own map behind the wheel, MMI free") is the
third tier and is not a solved feature on CarPlay. The first tier (Waze arrows
and distance in the cluster) is the realistic target.

## Static ABI gate for the guidance hook — PASS so far

`dio_manager_preload.c` hooks three iAP2 methods by mangled symbol. All three are
present in the firmware's `libesoiap2.so` (the library `dio_manager` loads):

- `iap2::CIAP2ControlSession::deployMessage(...)`  — present
- `iap2::CIAP2Link::sendToSession(...)`            — present
- `iap2::CIAP2ControlSessionModuleIdent::identificationInformation(...)` — present

None is in `dio_manager` or `libautoreceiver.so` directly, which is expected:
the hook attaches in the process but resolves into `libesoiap2.so`. This is a
name-level match only. It does not prove struct layouts, vtable offsets, or the
`CIAP2ControlSessionMessageView` ABI, which is the next static step and needs the
actual firmware binaries disassembled.

## The make-or-break question is app-side, not ours

The hook reads route-guidance TLVs the phone emits over iAP2. Whether **Waze**
emits them is independent of anything in this project. Apple Maps feeds the iAP2
route-guidance channel; several third-party nav apps render only to the CarPlay
screen and never emit route-guidance TLVs. The firmware's iAP2 control-session
modules seen by strings are EAP, HID, Power, OOBBTPairing and WifiShare — no
route-guidance module — consistent with route guidance being a message-stream
feature the app must opt into, not a unit capability.

If Waze does not emit iAP2 route guidance, the cluster shows nothing while Waze
navigates, and no code change on our side fixes that. This must be tested with
the phone before any cluster work is justified. It can be tested cheaply: the
hook's log path (`/tmp/dio_cluster.log`) records every TLV it sees.

## What can proceed without the car

1. iAP2 ABI/offset review of `dio_cluster.so` against the firmware `libesoiap2.so`
   (struct sizes, the message-view layout, the deployMessage signature). Static.
2. A capture-only card that also runs the TLV logger during a real Waze CarPlay
   session, to answer the Waze question from the phone. Read-only on the unit.

## What still blocks a real attempt

- The car runs a build whose `img_ver.txt` differs from the analysed package
  (42 vs 41 bytes, `G35S` vs `G35`). The real binaries must be captured and
  hashed before trusting any of the above for this car.
- Native ABI/offset compatibility is unproven.
- The independent-map tier has no working CarPlay precedent at all.

## ABI review, part 1: display routing for the mirror (2026-09-17)

The mirror renderer (`cluster.c`, internally `aa_cluster_mirror.c`) captures the
main HMI display with `screen_read_display` and blits it to displayable 33. The
capture source is the HMI display, so it is **source-agnostic**: it mirrors
whatever is on the main screen, CarPlay included. "Mirror the head unit to the
cluster" therefore does not depend on the Android Auto path.

Strong positive finding: the renderer's hard-coded target `displayable 33` is not
a Porsche-only constant. The firmware's own `org/dsi/ifc/displaymanagement/Constants`
defines `DISPLAYABLE_KOMBI_MAP_VIEW = 33`. The magic number the renderer writes to
matches, by name and value, the Audi firmware's identifier for the cluster map
surface. This is the first Q3-side confirmation that the renderer's display target
is meaningful on this platform, not just on Porsche.

Mechanics that match the firmware:
- Capture: `screen_read_display` on the HMI display (renderer expects 1920×720).
- Target: a Screen window with `SCREEN_PROPERTY_ID_STRING = "33"`, sized to the
  cluster; size auto-detected from displayable 33, default 1280×860.
- All Screen/EGL/GLES/NvMedia imports already matched 214/214 by name (report 05).

Still unproven, and each can break the mirror on the actual car:
- Whether displayable 33 on the Q3 is routable to the cluster and writable by a
  third-party window, or whether the factory cluster owns it exclusively.
- Contention: writing to 33 while the factory cluster renders there may flicker,
  fight for ownership, or be composited away. Upstream has Porsche handover logic
  (`IMapClusterService` suspend/restore) that must be validated for Audi.
- The real cluster resolution and the HMI capture permission on this unit.
- Struct/vtable ABI of the Screen and iAP2 calls (name match is not layout match).
- The car runs a build differing from the analysed package; confirm on real bytes.

Net: mirroring the head unit (with CarPlay on it) to the cluster is the most
statically supported tier. The display target is confirmed present in Audi
firmware. The open risks are display ownership/contention and native ABI, both
of which need the captured binaries and, ultimately, bench/vehicle validation.

## ABI review, part 2: native linkage of the mirror payload (2026-09-17)

Deeper than the 214/214 name match of report 05. Compared the upstream prebuilt
payload (`cluster`, `gal_cluster.so`, `dio_cluster.so` from the v0034 release)
against the firmware's graphics libraries extracted from stage-2 image-03. All
static linkage checks pass.

**ELF ABI flags identical.** Every payload and every firmware binary is
`EM_ARM, EABI5, soft-float, e_flags=0x5000202`. The float ABI matches, so
floating-point arguments cross the hook boundary intact; a soft/hard mismatch
(the classic silent corruptor) is ruled out.

**No symbol versioning.** The payloads declare no GNU version requirements, so
there is no symbol-version mismatch to resolve. QNX linkage is by plain name.

**Every entry point the mirror uses is exported by the firmware libraries:**

| Library (firmware, image-03) | Exports | Mirror calls checked | Result |
|---|---:|---|---|
| `libscreen.so.1` | 224 | `screen_read_display`, `screen_create_pixmap(+_buffer)`, `screen_get_display_property_iv`, `screen_get_context_property_pv`, `screen_create_context`, `screen_create_window`, `screen_set_window_property_iv/cv`, `screen_post_window`, `screen_get_buffer/pixmap_property_pv` | all present |
| `libEGL.so.1` | 35 | `eglGetDisplay`, `eglInitialize`, `eglCreateWindowSurface`, `eglMakeCurrent`, `eglSwapBuffers` | all present |
| `libGLESv2.so.2` | 316 | `glBindTexture`, `glTexImage2D`, `glTexSubImage2D`, `glDrawArrays` | all present |
| `libnvmedia.so` | 172 | `NvMediaDeviceCreate`, `NvMediaVideoDecoderCreateEx`, `NvMediaVideoDecoderRender`, `NvMediaVideoMixerCreate` | all present (the H.264 path, not needed for the plain mirror) |

Net: the mirror payload is link-compatible with the firmware graphics stack.
Nothing at the linker or ABI-flags level blocks it.

**What this does NOT prove, and what is now the whole remaining risk:**

1. **Display ownership/contention on surface 33.** Linkage says the calls
   resolve; it says nothing about whether a third-party window may own or share
   displayable 33 while the factory cluster renders there. This is the first
   thing that writes to the cluster and the main runtime unknown.
2. **Opaque-struct / Screen-version match.** The calls pass opaque handles, so
   field-offset ABI is not exercised by these signatures, but the payload was
   built against some Screen version; a different Screen minor on the car could
   still differ semantically. Confirm the firmware Screen version once captured.
3. **This is the package's libraries.** The car runs a build that differs
   (card 1). Card 2 captures the real libraries; rerun this exact check against
   them before trusting it for this vehicle.

Conclusion for the mirror: statically, it is as clear as it can get without the
car. The remaining gates are runtime display behaviour and the real-binary
recheck, both of which need the vehicle.
