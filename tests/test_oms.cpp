
#include <gtest/gtest.h>
#include "chronosx/oms.hpp"
#include "chronosx/risk_engine.hpp"

using namespace chronosx;

class OmsTest : public ::testing::Test {
protected:
    RiskEngine risk{RiskLimits{
        .max_order_qty = 1000,
        .max_order_notional = 1'000'000'000LL,
    }};

    OrderManagementSystem oms{risk};
};

// ---- Submit: valid orders ----

TEST_F(OmsTest, SubmitLimitBuyReturnsAssignedId) {
    auto resp = oms.submit({.side=Side::Buy, .type=OrderType::Limit,
                            .price=1000, .qty=10});

    EXPECT_NE(resp.assigned_id, kInvalidOrderId);
    EXPECT_TRUE(oms.order_exists(resp.assigned_id));
}

TEST_F(OmsTest, AutoIdMonotonicallyIncreases) {
    auto r1 = oms.submit({.side=Side::Buy, .type=OrderType::Limit,
                          .price=1000, .qty=10});
    auto r2 = oms.submit({.side=Side::Buy, .type=OrderType::Limit,
                          .price=1000, .qty=10});

    EXPECT_GT(r2.assigned_id, r1.assigned_id);
}

TEST_F(OmsTest, CallerProvidedIdIsHonoured) {
    auto resp = oms.submit({.id=42, .side=Side::Buy, .type=OrderType::Limit,
                            .price=1000, .qty=10});

    EXPECT_EQ(resp.assigned_id, OrderId{42});
}

TEST_F(OmsTest, SubmitSetsStatusNew) {
    auto resp = oms.submit({.side=Side::Buy, .type=OrderType::Limit,
                            .price=1000, .qty=10});
    auto status = oms.get_status(resp.assigned_id);

    ASSERT_TRUE(status.has_value());
    EXPECT_EQ(*status, OrderStatus::New);
}

TEST_F(OmsTest, SubmitMatchingOrdersResultInFilled) {
    auto sell = oms.submit({.id=1, .side=Side::Sell, .type=OrderType::Limit,
                            .price=1000, .qty=50});
    EXPECT_EQ(sell.match_result.final_status, OrderStatus::New);

    auto r2 = oms.submit({.id=2, .side=Side::Buy, .type=OrderType::Limit,
                          .price=1000, .qty=50});

    EXPECT_EQ(*oms.get_status(2), OrderStatus::Filled);
    ASSERT_EQ(r2.match_result.trades.size(), 1u);
}

// ---- Submit: validation rejection ----

TEST_F(OmsTest, ZeroQuantityIsRejected) {
    auto r = oms.submit({.side=Side::Buy, .type=OrderType::Limit,
                         .price=1000, .qty=0});

    EXPECT_EQ(r.match_result.final_status, OrderStatus::Rejected);
    EXPECT_TRUE(r.match_result.reject_event.has_value());
}

TEST_F(OmsTest, NonPositiveLimitPriceIsRejected) {
    auto r = oms.submit({.side=Side::Buy, .type=OrderType::Limit,
                         .price=0, .qty=10});

    EXPECT_EQ(r.match_result.final_status, OrderStatus::Rejected);
}

TEST_F(OmsTest, DuplicateIdIsRejected) {
    auto first = oms.submit({.id=7, .side=Side::Buy, .type=OrderType::Limit,
                             .price=1000, .qty=10});
    EXPECT_EQ(first.match_result.final_status, OrderStatus::New);

    auto r = oms.submit({.id=7, .side=Side::Buy, .type=OrderType::Limit,
                         .price=1000, .qty=10});

    EXPECT_EQ(r.match_result.final_status, OrderStatus::Rejected);
}

// ---- Submit: risk rejection ----

TEST_F(OmsTest, OversizedQtyIsRejectedByRisk) {
    auto r = oms.submit({.side=Side::Buy, .type=OrderType::Limit,
                         .price=1000, .qty=9999});

    EXPECT_EQ(r.match_result.final_status, OrderStatus::Rejected);
}

// ---- Cancel ----

TEST_F(OmsTest, CancelRestingOrder) {
    auto sub = oms.submit({.id=100, .side=Side::Buy, .type=OrderType::Limit,
                           .price=1000, .qty=50});

    auto can = oms.cancel(sub.assigned_id);

    EXPECT_TRUE(can.match_result.cancel_event.has_value());
    EXPECT_EQ(*oms.get_status(sub.assigned_id), OrderStatus::Cancelled);
}

TEST_F(OmsTest, CancelNonExistentIdIsRejected) {
    auto r = oms.cancel(9999);

    EXPECT_EQ(r.match_result.final_status, OrderStatus::Rejected);
}

TEST_F(OmsTest, CancelAlreadyFilledOrderIsRejected) {
    auto sell = oms.submit({.id=1, .side=Side::Sell, .type=OrderType::Limit,
                            .price=1000, .qty=10});
    EXPECT_EQ(sell.match_result.final_status, OrderStatus::New);

    auto buy = oms.submit({.id=2, .side=Side::Buy, .type=OrderType::Limit,
                           .price=1000, .qty=10});
    EXPECT_EQ(buy.match_result.final_status, OrderStatus::Filled);

    // Order 1 is now Filled — it cannot be cancelled.
    auto r = oms.cancel(1);

    EXPECT_NE(r.match_result.final_status, OrderStatus::Cancelled);
}

// ---- get_status ----

TEST_F(OmsTest, GetStatusReturnsNulloptForUnknownId) {
    EXPECT_FALSE(oms.get_status(0).has_value());
    EXPECT_FALSE(oms.get_status(12345).has_value());
}

// ---- Market order via OMS ----

TEST_F(OmsTest, MarketOrderDispatchedToEngine) {
    auto sell = oms.submit({.id=1, .side=Side::Sell, .type=OrderType::Limit,
                            .price=1000, .qty=20});
    EXPECT_EQ(sell.match_result.final_status, OrderStatus::New);

    auto r = oms.submit({.id=2, .side=Side::Buy, .type=OrderType::Market,
                         .price=0, .qty=20});

    ASSERT_EQ(r.match_result.trades.size(), 1u);
    EXPECT_EQ(*oms.get_status(2), OrderStatus::Filled);
}