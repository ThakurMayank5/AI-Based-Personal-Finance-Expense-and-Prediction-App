import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "@/context/auth-context";
import { api, type Prediction } from "@/lib/api";

export default function ForecastScreen() {
  const { token } = useAuth();
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setPrediction(await api.prediction(token));
    } catch (error) {
      Alert.alert(
        "Could not calculate forecast",
        error instanceof Error ? error.message : "Please try again.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);
  if (loading)
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color="#222222" />
      </View>
    );

  const shortHistory = (prediction?.history_months ?? 0) < 3;
  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              void load();
            }}
          />
        }
      >
        <Text style={styles.title}>Next month expenses</Text>
        <Text style={styles.subtitle}>
          Estimate based on completed monthly spending.
        </Text>
        <View style={styles.forecastCard}>
          <Text style={styles.month}>{prediction?.next_month}</Text>
          <Text style={styles.value}>
            ₹
            {(prediction?.forecast ?? 0).toLocaleString("en-IN", {
              maximumFractionDigits: 0,
            })}
          </Text>
          <Text style={styles.caption}>
            {shortHistory
              ? "Add at least three completed months for a forecast."
              : `Based on ${prediction?.history_months} completed months`}
          </Text>
        </View>

        <Pressable
          style={styles.refresh}
          onPress={() => {
            setRefreshing(true);
            void load();
          }}
        >
          <Text style={styles.refreshText}>Refresh forecast</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#FFFFFF" },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFFFFF",
  },
  content: {
    padding: 20,
    paddingBottom: 110,
    maxWidth: 680,
    width: "100%",
    alignSelf: "center",
  },
  title: { color: "#111111", fontSize: 26, fontWeight: "700", marginTop: 4 },
  subtitle: {
    color: "#666666",
    lineHeight: 20,
    marginTop: 6,
    marginBottom: 20,
  },
  forecastCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
    padding: 20,
    alignItems: "center",
  },
  month: { color: "#555555", fontWeight: "600", fontSize: 13 },
  value: {
    color: "#111111",
    fontSize: 36,
    fontWeight: "700",
    marginVertical: 8,
  },
  caption: { color: "#666666", textAlign: "center", lineHeight: 20 },
  infoCard: {
    marginTop: 16,
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
    backgroundColor: "#FFFFFF",
    padding: 16,
    gap: 10,
  },
  infoTitle: { color: "#111111", fontSize: 16, fontWeight: "700" },
  info: { color: "#555555", lineHeight: 20 },
  refresh: {
    borderWidth: 1,
    borderColor: "#222222",
    marginTop: 16,
    minHeight: 46,
    borderRadius: 4,
    justifyContent: "center",
    alignItems: "center",
  },
  refreshText: { color: "#222222", fontWeight: "600" },
});
