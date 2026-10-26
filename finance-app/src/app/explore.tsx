import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "@/context/auth-context";
import { api, type Transaction } from "@/lib/api";

const money = (amount: number) =>
  `₹${amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const today = () => new Date().toISOString().slice(0, 10);

export default function ActivityScreen() {
  const { token } = useAuth();
  const [items, setItems] = useState<Transaction[]>([]);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [transactionDate, setTransactionDate] = useState(today());
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setItems(await api.transactions(token));
    } catch (error) {
      Alert.alert(
        "Could not load expenses",
        error instanceof Error ? error.message : "Please try again.",
      );
    } finally {
      setRefreshing(false);
    }
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);

  async function add() {
    const parsed = Number(amount);
    if (!Number.isFinite(parsed) || parsed <= 0)
      return Alert.alert(
        "Enter an amount",
        "Use a positive number, for example 250.00.",
      );
    if (!token) return;
    setSaving(true);
    try {
      const created = await api.addTransaction(
        token,
        parsed,
        transactionDate,
        note,
      );
      setItems((current) => [created, ...current]);
      setAmount("");
      setNote("");
      setTransactionDate(today());
    } catch (error) {
      Alert.alert(
        "Could not add expense",
        error instanceof Error
          ? error.message
          : "Check the date format (YYYY-MM-DD).",
      );
    } finally {
      setSaving(false);
    }
  }

  function remove(item: Transaction) {
    Alert.alert(
      "Delete expense?",
      `${money(item.amount)} will be permanently removed.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            if (!token) return;
            try {
              await api.deleteTransaction(token, item.id);
              setItems((current) =>
                current.filter((entry) => entry.id !== item.id),
              );
            } catch (error) {
              Alert.alert(
                "Could not delete",
                error instanceof Error ? error.message : "Please try again.",
              );
            }
          },
        },
      ],
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
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
          <Text style={styles.title}>Add an expense</Text>
          <View style={styles.formCard}>
            <Text style={styles.label}>Amount</Text>
            <TextInput
              style={styles.amountInput}
              value={amount}
              onChangeText={setAmount}
              placeholder="0.00"
              placeholderTextColor="#888888"
              keyboardType="decimal-pad"
            />
            <Text style={styles.label}>Description</Text>
            <TextInput
              style={styles.input}
              value={note}
              onChangeText={setNote}
              placeholder="e.g. Groceries"
              placeholderTextColor="#888888"
            />
            <Text style={styles.label}>Date</Text>
            <TextInput
              style={styles.input}
              value={transactionDate}
              onChangeText={setTransactionDate}
              placeholder="YYYY-MM-DD"
              placeholderTextColor="#888888"
              autoCapitalize="none"
            />
            <Pressable
              onPress={() => void add()}
              disabled={saving}
              style={({ pressed }) => [
                styles.add,
                (saving || pressed) && styles.dimmed,
              ]}
            >
              {saving ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.addText}>Add expense</Text>
              )}
            </Pressable>
          </View>
          <Text style={styles.listTitle}>All expenses</Text>
          <View style={styles.listCard}>
            {items.length === 0 ? (
              <Text style={styles.empty}>Your expense list is empty.</Text>
            ) : (
              items.map((item) => (
                <Pressable
                  key={item.id}
                  onLongPress={() => remove(item)}
                  style={styles.row}
                >
                  <View style={styles.dot} />
                  <View style={styles.rowInfo}>
                    <Text style={styles.note}>{item.note || "Expense"}</Text>
                    <Text style={styles.date}>{item.date}</Text>
                  </View>
                  <Text style={styles.value}>{money(item.amount)}</Text>
                </Pressable>
              ))
            )}
          </View>
          {items.length > 0 && (
            <Text style={styles.deleteHint}>
              Long press an expense to delete it.
            </Text>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#FFFFFF" },
  flex: { flex: 1 },
  content: {
    padding: 20,
    paddingBottom: 110,
    maxWidth: 680,
    width: "100%",
    alignSelf: "center",
  },
  title: {
    color: "#111111",
    fontSize: 26,
    fontWeight: "700",
    marginTop: 4,
    marginBottom: 18,
  },
  formCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
    padding: 16,
    gap: 8,
  },
  label: { color: "#333333", fontSize: 13, fontWeight: "600", marginTop: 4 },
  input: {
    height: 46,
    borderColor: "#CFCFCF",
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 12,
    fontSize: 15,
    color: "#111111",
    marginBottom: 4,
  },
  amountInput: {
    height: 50,
    borderColor: "#CFCFCF",
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 12,
    fontSize: 20,
    fontWeight: "600",
    color: "#111111",
    marginBottom: 4,
  },
  add: {
    height: 48,
    borderRadius: 4,
    backgroundColor: "#222222",
    justifyContent: "center",
    alignItems: "center",
    marginTop: 7,
  },
  addText: { color: "#FFFFFF", fontWeight: "600", fontSize: 15 },
  dimmed: { opacity: 0.65 },
  listTitle: {
    color: "#111111",
    fontSize: 18,
    fontWeight: "700",
    marginVertical: 20,
  },
  listCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D4D4D4",
    borderRadius: 4,
    paddingHorizontal: 16,
  },
  row: {
    minHeight: 64,
    flexDirection: "row",
    alignItems: "center",
    borderBottomColor: "#E5E5E5",
    borderBottomWidth: 1,
    gap: 11,
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#333333" },
  rowInfo: { flex: 1 },
  note: { fontWeight: "600", color: "#222222" },
  date: { color: "#666666", fontSize: 12, marginTop: 3 },
  value: { fontWeight: "700", color: "#222222" },
  empty: { color: "#666666", textAlign: "center", marginVertical: 35 },
  deleteHint: {
    color: "#666666",
    textAlign: "center",
    marginTop: 12,
    fontSize: 12,
  },
});
