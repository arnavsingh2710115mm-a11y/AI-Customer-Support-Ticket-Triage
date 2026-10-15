export const confidence = (value: number) => (value * 100).toFixed(1) + '%';
export const metric = (value: number) => (value * 100).toFixed(2) + '%';
export const percent = (value: number) => (value * 100).toLocaleString(undefined, { maximumFractionDigits: 2 }) + '%';
export const count = (value: number) => value.toLocaleString();
