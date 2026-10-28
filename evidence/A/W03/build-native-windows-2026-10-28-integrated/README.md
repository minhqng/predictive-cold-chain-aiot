# W03 — Native build ESP-IDF v6.1 từ SOURCE TÍCH HỢP (2026-10-28)

> **Trạng thái:** `NATIVE BUILD PASS — INTEGRATED W03 SOURCE`
> **Kết luận:** `DONE` cho lớp biên dịch · phần vật lý `HARDWARE-LIMITED`
>
> Bundle này chứng minh **đúng mã nguồn firmware sẽ được giao** — worktree tích hợp
> `A-W03-integration` (HEAD `efe6075`, merge W02 `55fd67e` vào W03 `d54250c`) cộng toàn bộ
> thay đổi W03 còn chưa commit — biên dịch được bằng ESP-IDF v6.1 cho `esp32s3`.
> **KHÔNG** phải GitHub Actions CI và **KHÔNG** phải nghiệm thu phần cứng.

---

## 1. Vì sao cần bản build thứ ba

Các bundle trước đó:

| Bundle | Nguồn được build | Hạn chế |
|---|---|---|
| `build-native-windows-2026-10-27/` | `git archive f8587dd` | Không có thay đổi working tree |
| `build-native-windows-2026-10-28/` | Working tree **trước tích hợp** (`d54250c` + dirty) | Chưa có commit merge W02; chưa chứng minh cây tích hợp |
| **`build-native-windows-2026-10-28-integrated/`** (bundle này) | **Worktree tích hợp** `A-W03-integration` (HEAD `efe6075` + 28 file sửa + 7 file mới) | Chỉ là compile, không phải runtime |

Bundle này build **trực tiếp từ worktree tích hợp**, không copy cây trước merge, nên khớp
chính xác mã nguồn firmware sẽ được commit sau này.

## 2. Trạng thái nguồn tại thời điểm build

| Mục | Giá trị |
|---|---|
| Worktree | `C:\Users\dlbac\Downloads\coldguard-repo\A-W03-integration` |
| Nhánh | `integration/a-w03-w02-sync` |
| HEAD | `efe6075c6d7a7311f34f1a4241d5c4af21961e35` (merge commit, 2 parent: `d54250c` + `55fd67e`) |
| Staged diff SHA-256 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (rỗng) |
| Worktree diff SHA-256 | `836730ba326e4b935796730bb4093959e0c7de1d48ef55da7954f6f1b2dedd57` |
| Status SHA-256 | `28c2f7776ac9f6d819cf1d74d565195b82eac0609a1f9191a7819c591925eb3d` |
| Fingerprint cây `firmware/` | `a64fbca949a0b21e562315e91da951e360dd71c8c5f330a60a31b7aeb2cc2200` |
| Số file | 28 tracked sửa + 7 untracked (tại thời điểm build) |
| `sdkconfig` dùng để build | SHA-256 `8065e5836fff0328b43550148555ecd9ee679dd324c00a7d078763c5f9b049c2` (do `set-target` sinh ra, đã ghi hash rồi xoá khỏi cây nguồn) |
| `project_version` nhúng trong binary | `efe6075-dirty` |

Chi tiết: `raw/source-state.txt`, `raw/source-sha256.txt` (24 file `firmware/main/*`), và
`raw/project-description.txt` (trích đầu `project_description.json`).

> Lưu ý trung thực: bundle này được **thêm vào worktree sau khi build xong**. Nó chỉ chứa
> log/tài liệu, không chứa mã firmware, nên fingerprint `firmware/` `a64fbca9…` vẫn giữ nguyên.
> Số untracked trong `git status` hiện tại lớn hơn 7 vì có thêm chính bundle này.

## 3. Môi trường và lệnh

| Mục | Giá trị |
|---|---|
| Host | Windows 11 Pro 64-bit (build `10.0.26300`) |
| ESP-IDF | v6.1 tại `C:\Espressif\v6.1\esp-idf` |
| Profile | `C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1` |
| Target | `esp32s3` |
| Compiler | `xtensa-esp32s3-elf-gcc` 15.2.0 (`esp-15.2.0_20251204`) |
| Build dir | `C:\Users\dlbac\Downloads\coldguard-w03-integration-build-2026-10-28\build` (**ngoài** source tree) |

```powershell
$env:MSYSTEM=$null
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
idf.py -B C:\Users\dlbac\Downloads\coldguard-w03-integration-build-2026-10-28\build set-target esp32s3   # raw/10-set-target.log
idf.py -B C:\Users\dlbac\Downloads\coldguard-w03-integration-build-2026-10-28\build build                # raw/20-build.log
```

Cả hai lệnh thoát mã `0` (`set-target_exit=0`, `build_exit=0`).

## 4. Kết quả

| Hạng mục | Giá trị thực đo từ log |
|---|---|
| Thông điệp hoàn tất | `Project build complete.` |
| Bước Ninja | `1090/1090` |
| Warning trình biên dịch | `0` |
| Error trình biên dịch | `0` |
| `coldguard_firmware.bin` | `0x38920` bytes (231.712), trống `0xc76e0` bytes (816.864, 78%) |
| `bootloader.bin` | `0x5280` bytes (21.120), trống `0x2d80` bytes (36%) |
| Phân vùng app | `0x100000` bytes (1.048.576) |
| `partition-table.bin` | `0x3000` bytes (3.072) |

### 4.1. SHA-256 hiện vật nhị phân (từ thư mục build ngoài source)

| Hiện vật | SHA-256 |
|---|---|
| `build/coldguard_firmware.bin` | `50a43f98cd6d0043c854853fcd86e77e4f07c6381030f2631c7b36683b6b42bb` |
| `build/coldguard_firmware.elf` | `3319472d0377dd62c9b6a8beeb7387304d9dc90406cc37bfe7e955eb07305722` |
| `build/bootloader/bootloader.bin` | `3fb6a6731b00361af2dd12cfa6872b7505d3ee285423abbabf6c0b8c05d3ce72` |
| `build/partition_table/partition-table.bin` | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` (trùng bundle W02) |

Các hash này nhận diện binary sinh ra từ thư mục build ngoài source; **không** có binary nào
được nạp lên board.

### 4.2. Vì sao hash app khác bundle trước tích hợp

Bundle `build-native-windows-2026-10-28/` build **cùng byte** mã firmware (6 file
`firmware/main` từng sửa đều trùng hash; fingerprint cây firmware trùng) nhưng cho hash app
`38551966…`. Nguyên nhân: chuỗi phiên bản nhúng khác nhau (`d54250c-dirty` so với
`efe6075-dirty`) cùng timestamp build nhúng trong ảnh. Cùng mã nguồn biên dịch, khác metadata.

## 5. Toàn vẹn bundle

`SHA256SUMS.txt` phủ toàn bộ `raw/*`; `py verify_build.py` kiểm:

- hash từng file trong `SHA256SUMS.txt`;
- `Set Target to: esp32s3` trong `raw/10-set-target.log`;
- `Project build complete.` và marker `[1090/1090]`;
- dòng kích thước app `0x38920` / trống `0xc76e0` (78%);
- `project_version` = `efe6075-dirty` trong `raw/project-description.txt`;
- HEAD `efe6075c6d…` trong `raw/source-state.txt`;
- 0 warning / 0 error trong log build.

Chạy từ thư mục bundle:

```powershell
py -3 verify_build.py
```

## 6. Ranh giới

- Đây là **LOCAL native build**, không phải GitHub Actions CI. CI vẫn
  `INFRASTRUCTURE-LIMITED` (hạn mức thanh toán GitHub — `Billing & plans`).
- Compile chỉ chứng minh cú pháp/liên kết của cây tích hợp. Nó **không** kiểm tra mức logic
  RS-485, frame PZEM thật, hành vi cold-boot IBT-2, topology shunt hay TEC-OFF.
- **Không** cấp nguồn TEC, **không** tạo PWM, **không** flash. Các điều kiện an toàn điện
  trong `hardware-deviation-and-safety.md` giữ nguyên hiệu lực.

## 7. Tái lập

```powershell
$env:MSYSTEM=$null
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
cd C:\Users\dlbac\Downloads\coldguard-repo\A-W03-integration\firmware
idf.py -B C:\Users\dlbac\Downloads\coldguard-w03-integration-build-2026-10-28\build set-target esp32s3
idf.py -B C:\Users\dlbac\Downloads\coldguard-w03-integration-build-2026-10-28\build build

cd C:\Users\dlbac\Downloads\coldguard-repo\A-W03-integration\evidence\A\W03\build-native-windows-2026-10-28-integrated
py -3 verify_build.py
```
