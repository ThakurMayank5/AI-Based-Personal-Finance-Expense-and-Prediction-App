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
import { api, type Dashboard } from "@/lib/api";

const money = (amount: number) =>
  `₹${amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export default function DashboardScreen() {
  const { token, user, logout } = useAuth();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(async () => {
    if (!token) return;
    try {
      setData(await api.dashboard(token));
    } catch (error) {
      Alert.alert(
        "Could not load dashboard",
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
  if (loading && !data)
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color="#123C69" />
      </View>
    );
  const summary = data?.summary;
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
        <View style={styles.topline}>
          <View>
            <Text style={styles.greeting}>Welcome, {user?.display_name}</Text>
            <Text style={styles.title}>Dashboard</Text>
          </View>
          <Pressable onPress={() => void logout()} style={styles.logout}>
            <Text style={styles.logoutText}>Sign out</Text>
          </Pressable>
        </View>
        <View style={styles.totalCard}>
          <Text style={styles.cardLabel}>Monthly expenses</Text>
          <Text style={styles.total}>{money(summary?.total ?? 0)}</Text>
        </View>
        <Text style={styles.sectionTitle}>Six-month view</Text>
        <View style={styles.chartCard}>
          {(data?.monthly_totals ?? []).length === 0 ? (
            <Text style={styles.empty}>
              Add an expense to start building your monthly view.
            </Text>
          ) : (
            <MiniBars rows={data?.monthly_totals ?? []} />
          )}
        </View>
        <View style={styles.sectionRow}>
          <Text style={styles.sectionTitle}>Recent expenses</Text>
          <Text style={styles.hint}>See Activity tab</Text>
        </View>
        <View style={styles.recentCard}>
          {(data?.recent_transactions ?? []).length === 0 ? (
            <Text style={styles.empty}>No expenses yet.</Text>
          ) : (
            data?.recent_transactions.map((item) => (
              <View key={item.id} style={styles.row}>
                <View style={styles.icon}>
                  <Text>₹</Text>
                </View>
                <View style={styles.rowText}>
                  <Text style={styles.note}>{item.note || "Expense"}</Text>
                  <Text style={styles.date}>{item.date}</Text>
                </View>
                <Text style={styles.amount}>{money(item.amount)}</Text>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
function MiniBars({ rows }: { rows: { month: string; total: number }[] }) {
  const max = Math.max(...rows.map((row) => row.total), 1);
  return (
    <View style={styles.bars}>
      {rows.map((row) => (
        <View key={row.month} style={styles.barColumn}>
          <View style={styles.barSlot}>
            <View
              style={[
                styles.bar,
                { height: `${Math.max(8, (row.total / max) * 100)}%` },
              ]}
            />
          </View>
          <Text style={styles.barLabel}>{row.month.slice(5)}</Text>
        </View>
      ))}
    </View>
  );
}
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#FFFFFF" },
  content: {
    padding: 20,
    paddingBottom: 110,
    gap: 20,
    maxWidth: 680,
    alignSelf: "center",
    width: "100%",
  },
  loading: {
    flex: 1,
    backgroundColor: "#FFFFFF",
    justifyContent: "center",
    alignItems: "center",
  },
  topline: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  greeting: { color: "#666666", fontSize: 14 },
  title: { color: "#111111", fontSize: 26, fontWeight: "700", marginTop: 2 },
  logout: {
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
  },
  logoutText: { color: "#222222", fontWeight: "600", fontSize: 13 },
  totalCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
    padding: 20,
  },
  cardLabel: { color: "#555555", fontSize: 13, fontWeight: "600" },
  total: {
    color: "#111111",
    fontSize: 34,
    fontWeight: "700",
    marginVertical: 8,
  },
  changeText: { color: "#555555", fontSize: 13 },
  transactionCount: { color: "#666666", marginTop: 10, fontSize: 13 },
  sectionTitle: { color: "#111111", fontSize: 18, fontWeight: "700" },
  sectionRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  hint: { color: "#666666", fontSize: 12 },
  chartCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
    padding: 16,
    minHeight: 175,
  },
  bars: {
    flex: 1,
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-end",
    justifyContent: "space-around",
  },
  barColumn: { flex: 1, alignItems: "center", gap: 8 },
  barSlot: { height: 110, width: "100%", justifyContent: "flex-end" },
  bar: { backgroundColor: "#222222", borderRadius: 0, minHeight: 8 },
  barLabel: { color: "#666666", fontSize: 11 },
  recentCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
    paddingHorizontal: 16,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: "#E5E5E5",
    gap: 11,
  },
  icon: {
    width: 30,
    height: 30,
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
    alignItems: "center",
    justifyContent: "center",
  },
  rowText: { flex: 1 },
  note: { color: "#222222", fontWeight: "600", fontSize: 14 },
  date: { color: "#666666", marginTop: 2, fontSize: 12 },
  amount: { color: "#222222", fontWeight: "700" },
  empty: {
    color: "#666666",
    alignSelf: "center",
    marginVertical: 35,
    textAlign: "center",
  },
});
