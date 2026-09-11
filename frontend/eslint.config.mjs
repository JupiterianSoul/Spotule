import nextConfig from "eslint-config-next";
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const config = [...nextConfig, ...nextCoreWebVitals, { ignores: [".next/**", "node_modules/**"] }];
export default config;
