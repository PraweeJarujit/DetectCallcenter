/* AudioWorklet: ส่งเสียงดิบ (mono) จากไมค์ / เสียงระบบ / สายตัวอย่าง กลับไปให้ live.js ทีละบล็อก */
class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    const channels = inputs[0];
    if (channels && channels.length && channels[0].length) {
      const n = channels[0].length;
      const mono = new Float32Array(n);
      for (const ch of channels) for (let i = 0; i < n; i++) mono[i] += ch[i] / channels.length;
      this.port.postMessage(mono, [mono.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
