import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.enterprise.mobile",
  appName: "Enterprise",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
};

export default config;
