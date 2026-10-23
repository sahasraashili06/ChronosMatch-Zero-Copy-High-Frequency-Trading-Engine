
#include <gtest/gtest.h>
#include "chronosx/matching_engine.hpp"

using namespace chronosx;

// ---- Fixture ----

class MatchingEngineTest : public ::testing::Test {
protected:
    MatchingEngine engine;
};

// ============================================================
// No-match: order rests in book
// ============================================================

TEST_F(MatchingEngineTest, LimitBuyRestsWhenNoBestAsk) {
    auto r = engine.submit_limit(1, Side::Buy, 1000, 10);

    EXPECT_TRUE(r.trades.empty());
    EXPECT_EQ(r.final_status, OrderStatus::New);
    EXPECT_EQ(*engine.book().best_bid(), Price{1000});
}

TEST_F(MatchingEngineTest, LimitSellRestsWhenNoBestBid) {
    auto r = engine.submit_limit(1, Side::Sell, 1050, 10);

    EXPECT_TRUE(r.trades.empty());
    EXPECT_EQ(r.final_status, OrderStatus::New);
    EXPECT_EQ(*engine.book().best_ask(), Price{1050});
}

TEST_F(MatchingEngineTest, LimitBuyBelowBestAskDoesNotMatch) {
    (void)engine.submit_limit(1, Side::Sell, 1050, 10);

    auto r = engine.submit_limit(2, Side::Buy, 1040, 10);

    EXPECT_TRUE(r.trades.empty());
    EXPECT_EQ(r.final_status, OrderStatus::New);
}

// ============================================================
// Exact match
// ============================================================

TEST_F(MatchingEngineTest, ExactFillOneSellOneBy) {

    auto resting = engine.submit_limit(1, Side::Sell, 1000, 50);
    EXPECT_EQ(resting.final_status, OrderStatus::New);


    auto r = engine.submit_limit(2, Side::Buy, 1000, 50);

    ASSERT_EQ(r.trades.size(), 1u);
    EXPECT_EQ(r.trades[0].aggressor_id, OrderId{2});
    EXPECT_EQ(r.trades[0].resting_id, OrderId{1});
    EXPECT_EQ(r.trades[0].price, Price{1000});
    EXPECT_EQ(r.trades[0].qty, Quantity{50});
    EXPECT_EQ(r.final_status, OrderStatus::Filled);
    EXPECT_TRUE(engine.book().is_empty());
}

TEST_F(MatchingEngineTest, ExecutionAtRestingPrice_MakerPrice) {
    auto resting = engine.submit_limit(1, Side::Sell, 1000, 10);
    EXPECT_EQ(resting.final_status, OrderStatus::New);

    auto r = engine.submit_limit(2, Side::Buy, 1050, 10);

    ASSERT_EQ(r.trades.size(), 1u);
    EXPECT_EQ(r.trades[0].price, Price{1000});  // Maker price
}

// ============================================================
// Partial fills
// ============================================================

TEST_F(MatchingEngineTest, AggressorPartiallyFillsAndRests) {
    auto resting = engine.submit_limit(1, Side::Sell, 1000, 30);
    EXPECT_EQ(resting.final_status, OrderStatus::New);

    auto r = engine.submit_limit(2, Side::Buy, 1000, 50);

    ASSERT_EQ(r.trades.size(), 1u);
    EXPECT_EQ(r.trades[0].qty, Quantity{30});
    EXPECT_EQ(r.final_status, OrderStatus::PartiallyFilled);

    // Residual 20 should rest in the book.
    EXPECT_EQ(engine.book().bid_qty_at(1000), Quantity{20});
}

TEST_F(MatchingEngineTest, RestingOrderPartiallyFilled) {
    auto resting = engine.submit_limit(1, Side::Sell, 1000, 50);
    EXPECT_EQ(resting.final_status, OrderStatus::New);

    auto r = engine.submit_limit(2, Side::Buy, 1000, 20);

    ASSERT_EQ(r.trades.size(), 1u);
    EXPECT_EQ(r.trades[0].qty, Quantity{20});
    EXPECT_EQ(r.final_status, OrderStatus::Filled);

    // Resting sell should have 30 remaining.
    EXPECT_EQ(engine.book().ask_qty_at(1000), Quantity{30});
}

// ============================================================
// Multi-level sweep
// ============================================================

TEST_F(MatchingEngineTest, BuySweepsMultipleAskLevels) {
    (void)engine.submit_limit(10, Side::Sell, 1000, 20);
    (void)engine.submit_limit(11, Side::Sell, 1010, 20);
    (void)engine.submit_limit(12, Side::Sell, 1020, 20);

    // Buy 55 across three levels: 20 + 20 + 15 = 55.
    auto r = engine.submit_limit(20, Side::Buy, 1020, 55);

    ASSERT_EQ(r.trades.size(), 3u);
    EXPECT_EQ(r.trades[0].price, Price{1000});
    EXPECT_EQ(r.trades[0].qty, Quantity{20});
    EXPECT_EQ(r.trades[1].price, Price{1010});
    EXPECT_EQ(r.trades[1].qty, Quantity{20});
    EXPECT_EQ(r.trades[2].price, Price{1020});
    EXPECT_EQ(r.trades[2].qty, Quantity{15});
    EXPECT_EQ(r.final_status, OrderStatus::Filled);
}

TEST_F(MatchingEngineTest, FIFOWithinPriceLevel) {
    (void)engine.submit_limit(1, Side::Sell, 1000, 10);
    (void)engine.submit_limit(2, Side::Sell, 1000, 10);

    auto r = engine.submit_limit(3, Side::Buy, 1000, 15);

    ASSERT_GE(r.trades.size(), 1u);
    EXPECT_EQ(r.trades[0].resting_id, OrderId{1});
}

// ============================================================
// Market orders
// ============================================================

TEST_F(MatchingEngineTest, MarketOrderFullFill) {
    auto resting = engine.submit_limit(1, Side::Sell, 1000, 50);
    EXPECT_EQ(resting.final_status, OrderStatus::New);

    auto r = engine.submit_market(2, Side::Buy, 50);

    ASSERT_EQ(r.trades.size(), 1u);
    EXPECT_EQ(r.trades[0].qty, Quantity{50});
    EXPECT_EQ(r.final_status, OrderStatus::Filled);
}

TEST_F(MatchingEngineTest, MarketOrderIOCCancelsResidual) {
    auto resting = engine.submit_limit(1, Side::Sell, 1000, 20);
    EXPECT_EQ(resting.final_status, OrderStatus::New);

    auto r = engine.submit_market(2, Side::Buy, 50);

    ASSERT_EQ(r.trades.size(), 1u);
    EXPECT_EQ(r.trades[0].qty, Quantity{20});
    EXPECT_TRUE(r.cancel_event.has_value());
    EXPECT_EQ(r.cancel_event->remaining_qty, Quantity{30});

    // Some quantity filled before the residual was cancelled.
    EXPECT_EQ(r.final_status, OrderStatus::PartiallyFilled);
}

TEST_F(MatchingEngineTest, MarketOrderOnEmptyBookCancelled) {
    auto r = engine.submit_market(1, Side::Buy, 100);

    EXPECT_TRUE(r.trades.empty());
    EXPECT_TRUE(r.cancel_event.has_value());
    EXPECT_EQ(r.final_status, OrderStatus::Cancelled);
}

// ============================================================
// Cancel
// ============================================================

TEST_F(MatchingEngineTest, CancelRestingOrder) {
    auto resting = engine.submit_limit(1, Side::Buy, 1000, 100);
    EXPECT_EQ(resting.final_status, OrderStatus::New);

    auto r = engine.cancel_order(1);

    EXPECT_TRUE(r.cancel_event.has_value());
    EXPECT_EQ(r.cancel_event->order_id, OrderId{1});
    EXPECT_EQ(r.final_status, OrderStatus::Cancelled);
    EXPECT_FALSE(engine.book().best_bid().has_value());
}

TEST_F(MatchingEngineTest, CancelNonExistentOrder) {
    auto r = engine.cancel_order(999);

    EXPECT_TRUE(r.reject_event.has_value());
    EXPECT_EQ(r.final_status, OrderStatus::Rejected);
}

TEST_F(MatchingEngineTest, CancelThenMatchDoesNotUseRemovedOrder) {
    (void)engine.submit_limit(1, Side::Sell, 1000, 50);
    (void)engine.cancel_order(1);

    auto r = engine.submit_limit(2, Side::Buy, 1000, 50);

    EXPECT_TRUE(r.trades.empty());
    EXPECT_EQ(r.final_status, OrderStatus::New);
}

// ============================================================
// Invariants
// ============================================================

TEST_F(MatchingEngineTest, NoCrossedBookAfterMatch) {
    (void)engine.submit_limit(1, Side::Sell, 1000, 20);
    (void)engine.submit_limit(2, Side::Buy, 1000, 30);

    auto bb = engine.book().best_bid();
    auto ba = engine.book().best_ask();

    if (bb && ba) {
        EXPECT_LT(*bb, *ba);
    }
}

TEST_F(MatchingEngineTest, SeqCounterMonotonicallyIncreases) {
    uint64_t before = engine.seq_counter();

    (void)engine.submit_limit(1, Side::Buy, 1000, 10);

    EXPECT_GT(engine.seq_counter(), before);
}
