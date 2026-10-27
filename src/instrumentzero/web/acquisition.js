/* Shared acquisition transforms. No device access occurs in this module.
 * Node acceptance fixtures exercise these exact functions with synthetic inputs.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.InstrumentZeroAcquisition = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function createCaptureGate() {
    let generation = 0;
    const snapshot = () => {
      const selected = generation;
      return Object.freeze({isCurrent: () => selected === generation});
    };
    return Object.freeze({begin() { generation++; return snapshot(); }, cancel() { generation++; }, snapshot});
  }

  function stopStream(stream) {
    if (stream) for (const track of stream.getTracks()) track.stop();
  }

  function markerROI(width, height, marker, radius = 25) {
    if (![width, height, radius].every(Number.isInteger) || width < 1 || height < 1 || radius < 2 ||
        !marker || !Number.isFinite(marker.x) || !Number.isFinite(marker.y)) return null;
    const size = radius * 2, x = Math.round(marker.x) - radius, y = Math.round(marker.y) - radius;
    if (x < 0 || y < 0 || x + size > width || y + size > height) return null;
    return {x, y, width: size, height: size};
  }

  function locateDarkMarker(rgba, roi, {threshold = 65, minPixels = 4, maxDarkFraction = .7,
                                     maxMotionPx = 15} = {}) {
    if (!roi || !Number.isInteger(roi.width) || !Number.isInteger(roi.height) ||
        roi.width < 1 || roi.height < 1 || rgba?.length !== roi.width * roi.height * 4) {
      throw new Error('Marker pixels must match a complete in-frame RGBA region.');
    }
    const width = roi.width, height = roi.height, count = width * height;
    const weights = new Float64Array(count), visited = new Uint8Array(count);
    let dark = 0;
    for (let i = 0; i < count; i++) {
      const p = i * 4, gray = .299 * rgba[p] + .587 * rgba[p + 1] + .114 * rgba[p + 2];
      // Transparent canvas padding is not a physical black marker.
      if (rgba[p + 3] >= 128 && gray < threshold) { weights[i] = threshold - gray; dark++; }
    }
    if (dark < minPixels || dark >= count * maxDarkFraction) {
      return {found: false, reason: 'No isolated dark fiducial in the selected region.'};
    }
    const components = [];
    for (let first = 0; first < count; first++) {
      if (!weights[first] || visited[first]) continue;
      const queue = [first]; visited[first] = 1;
      let total = 0, sx = 0, sy = 0, pixels = 0;
      for (let head = 0; head < queue.length; head++) {
        const i = queue[head], x = i % width, y = Math.floor(i / width), weight = weights[i];
        total += weight; sx += x * weight; sy += y * weight; pixels++;
        const neighbors = [];
        if (x > 0) neighbors.push(i - 1);
        if (x < width - 1) neighbors.push(i + 1);
        if (y > 0) neighbors.push(i - width);
        if (y < height - 1) neighbors.push(i + width);
        for (const j of neighbors) if (weights[j] && !visited[j]) { visited[j] = 1; queue.push(j); }
      }
      if (pixels >= minPixels && pixels < count * maxDarkFraction) {
        const x = sx / total, y = sy / total;
        components.push({x, y, pixels, distance: Math.hypot(x - width / 2, y - height / 2)});
      }
    }
    components.sort((a, b) => a.distance - b.distance);
    const selected = components[0];
    if (!selected || selected.distance > maxMotionPx) {
      return {found: false, reason: 'Fiducial lost or moved too far between frames. Select it again.'};
    }
    return {found: true, x: roi.x + selected.x, y: roi.y + selected.y, pixels: selected.pixels};
  }

  function settledPosition(values, noisePx, minSamples = 10) {
    if (!Array.isArray(values) || values.length < minSamples || !values.every(Number.isFinite)) {
      throw new Error(`Wait for at least ${minSamples} valid tracked frames.`);
    }
    if (!Number.isFinite(noisePx) || noisePx <= 0) throw new Error('Position noise must be positive.');
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const spread = Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
                             Math.max(1, values.length - 1));
    if (spread > 3 * noisePx) throw new Error('Marker is not settled relative to the declared position noise.');
    return {mean, spread, samples: values.length};
  }

  function prepareAudioInput(channels, inputRate, {targetRate = 16000, maxDuration = 20} = {}) {
    if (!Number.isFinite(inputRate) || inputRate < 8000 || inputRate > 192000 ||
        !Number.isFinite(targetRate) || targetRate < 8000 || targetRate > 192000 ||
        !Number.isFinite(maxDuration) || maxDuration <= 0 || maxDuration > 20) {
      throw new Error('Audio rates must be 8–192 kHz and the duration limit must be at most 20 seconds.');
    }
    if (!Array.isArray(channels) || !channels.length || channels.length > 32 ||
        !channels.every(channel => channel && Number.isInteger(channel.length) && channel.length > 0 &&
                                  channel.length === channels[0].length)) {
      throw new Error('Audio channels must contain equal, nonempty sample arrays.');
    }
    const originalLength = channels[0].length;
    const length = Math.min(originalLength, Math.floor(inputRate * maxDuration));
    if (length < 1) throw new Error('No audio samples were available.');
    const samples = new Float32Array(length);
    for (let i = 0; i < length; i++) {
      let value = 0;
      for (const channel of channels) {
        if (!Number.isFinite(channel[i])) throw new Error('Audio contains a nonfinite sample.');
        value += channel[i] / channels.length;
      }
      samples[i] = value;
      if (!Number.isFinite(samples[i])) throw new Error('Audio sample is nonfinite in the float32 acquisition format.');
    }
    return {samples, inputRate, targetRate, outputLength: Math.max(1, Math.floor(length * targetRate / inputRate)),
            duration: length / inputRate, originalDuration: originalLength / inputRate,
            truncated: length < originalLength, channelCount: channels.length};
  }

  async function prepareDecodedAudio(decoded, options = {}, createOfflineContext) {
    const channels = Array.from({length: decoded.numberOfChannels}, (_, i) => decoded.getChannelData(i));
    const input = prepareAudioInput(channels, decoded.sampleRate, options);
    if (input.inputRate === input.targetRate) return {...input, sampleRate: input.targetRate};
    // Use the browser's established resampler, not a naïve stride that aliases high frequencies.
    const makeContext = createOfflineContext || ((channels, length, rate) => new OfflineAudioContext(channels, length, rate));
    const offline = makeContext(1, input.outputLength, input.targetRate);
    const buffer = offline.createBuffer(1, input.samples.length, input.inputRate);
    buffer.copyToChannel(input.samples, 0);
    const source = offline.createBufferSource(); source.buffer = buffer;
    source.connect(offline.destination); source.start();
    const rendered = await offline.startRendering();
    const samples = new Float32Array(rendered.getChannelData(0));
    if (samples.length !== input.outputLength || !samples.every(Number.isFinite)) {
      throw new Error('Browser resampling did not return the declared finite sample count.');
    }
    return {...input, samples, sampleRate: input.targetRate};
  }

  function joinAudioChunks(chunks) {
    if (!Array.isArray(chunks) || !chunks.length) throw new Error('No microphone samples were captured.');
    const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const samples = new Float32Array(length);
    let offset = 0;
    for (const chunk of chunks) { samples.set(chunk, offset); offset += chunk.length; }
    return samples;
  }

  return Object.freeze({createCaptureGate, stopStream, markerROI, locateDarkMarker, settledPosition,
                        prepareAudioInput, prepareDecodedAudio, joinAudioChunks});
});
