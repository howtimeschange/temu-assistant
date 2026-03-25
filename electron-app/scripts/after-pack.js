/**
 * after-pack.js — electron-builder afterPack hook
 *
 * 在打包完成后，把对应平台/架构的 Python 解释器复制到 app Resources/python 目录。
 * python-dist/ 结构：
 *   mac-arm64/  → macOS arm64 Python
 *   mac-x64/    → macOS x64 Python
 *   win-x64/    → Windows x64 Python
 */

const fs   = require('fs')
const path = require('path')

exports.default = async function afterPack(context) {
  const { electronPlatformName, arch, appOutDir } = context

  // arch: 0=ia32, 1=x64, 2=armv7l, 3=arm64, 4=universal, 5=mips, 6=mipsel
  const archName = arch === 3 ? 'arm64' : 'x64'

  let srcKey
  if (electronPlatformName === 'darwin') {
    srcKey = archName === 'arm64' ? 'mac-arm64' : 'mac-x64'
  } else if (electronPlatformName === 'win32') {
    srcKey = 'win-x64'
  } else {
    console.log(`[after-pack] skip unsupported platform: ${electronPlatformName}`)
    return
  }

  const scriptDir = path.dirname(__dirname)  // electron-app/
  const srcPython = path.join(scriptDir, 'python-dist', srcKey)

  if (!fs.existsSync(srcPython)) {
    console.warn(`[after-pack] WARN: bundled Python not found at ${srcPython}, skipping`)
    console.warn(`[after-pack] Run scripts/download-python.sh to download Python for all platforms`)
    return
  }

  // 目标路径：Resources/python/
  let resourcesPath
  if (electronPlatformName === 'darwin') {
    resourcesPath = path.join(appOutDir, `${context.packager.appInfo.productFilename}.app`, 'Contents', 'Resources')
  } else {
    resourcesPath = path.join(appOutDir, 'resources')
  }

  const destPython = path.join(resourcesPath, 'python')
  console.log(`[after-pack] Copying Python ${srcKey} → ${destPython}`)

  fs.mkdirSync(destPython, { recursive: true })
  copyDirSync(srcPython, destPython)
  console.log(`[after-pack] Python bundled successfully (${srcKey})`)
}

function copyDirSync(src, dest) {
  const entries = fs.readdirSync(src, { withFileTypes: true })
  for (const entry of entries) {
    const s = path.join(src, entry.name)
    const d = path.join(dest, entry.name)
    if (entry.isDirectory()) {
      fs.mkdirSync(d, { recursive: true })
      copyDirSync(s, d)
    } else if (entry.isSymbolicLink()) {
      // On Windows, symlink creation requires elevated privileges and often fails.
      // Resolve the symlink and copy the actual file content instead.
      try {
        const realSrc = fs.realpathSync(s)
        fs.copyFileSync(realSrc, d)
      } catch (e) {
        // Fallback: try creating symlink (may work on Unix/macOS)
        try {
          const target = fs.readlinkSync(s)
          if (fs.existsSync(d)) fs.unlinkSync(d)
          fs.symlinkSync(target, d)
        } catch (e2) {
          console.warn(`[after-pack] WARN: could not copy symlink ${s} → ${d}: ${e2.message}`)
        }
      }
    } else {
      fs.copyFileSync(s, d)
    }
  }
}
